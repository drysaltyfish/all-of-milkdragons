# check_domains.py
import hashlib
import json
import os
import re
import threading
import time
from datetime import date
from itertools import chain, product
from urllib.parse import unquote, urljoin, urlparse

import random
import idna
import dns.resolver
import requests
import urllib3
from bs4 import BeautifulSoup
from tqdm.contrib.concurrent import thread_map

from const import *
from community import (
    STORE_PATH as COMMUNITY_JSON,
    classify_landing,
    load as load_community,
    save as save_community,
    target_domains as community_target_domains,
)

# ==================== HTTP 客户端：浏览器 TLS 指纹 ====================
# ★ 为什么需要：有一批域名（奶蛙大学.com / .website、芜湖奶龙大学.icu、
#   深圳奶龙大学.com、黑龙江奶龙大学.com、吉林奶蛙大学.com……）用 requests
#   请求稳定返回 403，可同一时刻用 curl 带**一模一样**的请求头请求就是 200。
#   对端根本没看请求头 —— 它看的是 TLS 握手指纹（JA3/JA4）：requests 用的是
#   Python ssl 的默认套件表，一眼就是脚本。curl_cffi 直接复用 Chrome 的
#   ClientHello，所以能过。
#
# ★ 装不上 curl_cffi 也能跑（自动退回 requests），单测和本地环境不必依赖它，
#   只是上面那批站点仍然会 403。
try:
    from curl_cffi import requests as browser_requests

    HAS_BROWSER_FINGERPRINT = True
except ImportError:  # pragma: no cover
    browser_requests = None
    HAS_BROWSER_FINGERPRINT = False

# 伪装成哪个浏览器的指纹。curl_cffi 会持续跟进新版本，用一个稳的即可。
IMPERSONATE = "chrome"

urllib3.disable_warnings()

# ---------- 配置 ----------
DNS_WORKERS = 500
# ★ 从 200 降到 48。
#   176 个奶龙域名里有一大批挂在同一个「域名停放/跳转」服务后面
#   （单看 15.197.162.184 一个 IP 上就挤了 11 个域名），200 个线程一股脑
#   打过去会触发对方的限流：返回 403 / 412 / 429，或者干脆掐断连接。
#   结果是一堆本来活得好好的域名被记成「打不开」——线上实测 34 个「打不开」
#   里有 20 个当时用同样的请求头再发一次就是 200。降并发 + 阶段 2.5 复检，
#   既不慢又能把误判捡回来。
HTTP_WORKERS = 48

# 单个 DNS 服务器的等待时间 / 一次解析的总预算。
# ★ 这两个值必须分开：dnspython 的 lifetime 是整次解析的预算，
#   如果 lifetime == timeout，第一个服务器超时就吃光预算、根本轮不到后面的服务器。
#   这曾导致 CI（海外 runner，前两跳 DNS 容易抖）稳定丢掉三成域名。
DNS_TIMEOUT = 3
DNS_LIFETIME = 9
DNS_ATTEMPTS = 2          # 一轮失败后换服务器偏移再试一次
HTTP_TIMEOUT = 30

# ★ 只放**从 runner 一定连得上**的解析器。
#   dnspython 会在 nameservers 之间轮转，一个连不上的服务器每次都要白等满
#   DNS_TIMEOUT，轮到时还可能把 lifetime 耗光、连后面的好服务器都试不到 ——
#   这比少配一个服务器糟糕得多。（曾被 223.5.5.5 / 119.29.29.29 坑掉 41 个域名。）
DNS_SERVERS = ["8.8.8.8", "1.1.1.1"]

# 复检（上一轮有记录、本轮没查到的域名）用的慢节奏参数
DNS_RESCUE_WORKERS = 60
DNS_RESCUE_TIMEOUT = 5
DNS_RESCUE_LIFETIME = 20

# HTTP 复检：把「像是被限流 / 超时」的行换个慢节奏重跑一遍。
# ★ 8 而不是 4：这一轮不再退避（见 tiers=0），纯串行等待没有意义，
#   稍微给点并发既快又不会重新制造一次突发。
HTTP_RETRY_WORKERS = 8
HTTP_RETRY_JITTER = 1.5
# 这些状态码基本都是临时性的（限流 / 人机挑战 / 网关抖动），重试有意义。
# 404 / 400 这种是站点自己说的「没有」，重试也不会变，不浪费请求。
TRANSIENT_STATUS = {403, 408, 412, 425, 429, 500, 502, 503, 504, 520, 521, 522, 524}

# ---------- 指数退避 ----------
# 三级退避：5s -> 15s -> 30s（第三级正好撞到上限）。
# 封顶 30s 的理由：抓取是几十个线程并行的，单个域名退避太久只会把整个阶段拖长；
# 而「对端限流」这类问题秒级就能恢复，等更久并没有额外收益。
BACKOFF_TIERS = 3
BACKOFF_BASE = 5.0
BACKOFF_FACTOR = 3.0
BACKOFF_MAX = 30.0
BACKOFF_JITTER = 0.25      # ±25% 抖动：多线程一起退避时别又攒成一波

# ---------- 历史数据保留 ----------
# 一周目抓不到的域名不立刻删：先留着、记下失联时间，连续失联超过这么多天才移除。
# 这样偶发的网络抖动/限流不会让卡片每天在墙上忽隐忽现。
RETENTION_DAYS = 3

OUT_JSON = "result.json"
LOGO_DIR = "logos"

MAX_HOPS = 5
MAX_HTML = 300_000_000_000
MAX_HTML_BODY = 2_000_000_000     # title/logo 解析用，可稍大
MIN_LOGO_BYTES = 64           # 太小的当失败
# ★ 校徽体积上限。以前只查了下界，配上 process_logos.py 里为了处理
#   8072×1670 大图而放开的解压炸弹保护（Image.MAX_IMAGE_PIXELS = None），
#   一个超大图就能把 CI 的内存或磁盘打爆。模板域名基本是同一个人的，
#   这是理论问题；一旦开放投稿，它就是现成的 DoS 口子。
MAX_LOGO_BYTES = 4 * 1024 * 1024


# ==================== 域名构造 ====================
def to_ascii(domain: str) -> str | None:
    try:
        return idna.encode(domain).decode("ascii")
    except idna.IDNAError:
        return None


def build_targets(tree, cn_tlds, en_tlds):
    prefixes = ["".join(combo) for combo in product(*tree)]
    seen, result = set(), []
    for p in prefixes:
        for tld in (*cn_tlds, *en_tlds):
            u = f"{p}.{tld}"
            a = to_ascii(u)
            if not a or a in seen:
                continue
            seen.add(a)
            result.append((u, a))
    return result


# ==================== 线程本地对象 ====================
_tl = threading.local()


def get_resolver():
    if not hasattr(_tl, "resolver"):
        r = dns.resolver.Resolver()
        r.timeout = DNS_TIMEOUT
        r.lifetime = DNS_LIFETIME
        r.nameservers = DNS_SERVERS
        _tl.resolver = r
    return _tl.resolver


def get_session():
    """★ 每个线程一个 Session，带完整浏览器请求头 + 浏览器 TLS 指纹。"""
    if not hasattr(_tl, "session"):
        if HAS_BROWSER_FINGERPRINT:
            s = browser_requests.Session(impersonate=IMPERSONATE)
        else:
            s = requests.Session()
        s.headers.update(DEFAULT_HEADERS)   # 完整 UA / Accept / Sec-Fetch-* 等
        try:
            s.max_redirects = MAX_HOPS
        except Exception:                   # pragma: no cover - 个别版本不让设
            pass
        _tl.session = s
    return _tl.session


# ==================== 指数退避 ====================
def backoff_delay(attempt: int) -> float:
    """第 attempt 级退避该等多久（attempt 从 0 开始）。纯函数，方便单测。

    base=5 / factor=3 -> 5s, 15s, 30s（5*3**2=45 被上限截到 30）
    """
    return min(BACKOFF_MAX, BACKOFF_BASE * (BACKOFF_FACTOR ** attempt))


def sleep_backoff(attempt: int) -> None:
    """带抖动的退避睡眠。多线程同时退避时，别让它们退避完又同时发出去。"""
    delay = backoff_delay(attempt)
    time.sleep(delay * (1.0 + random.uniform(-BACKOFF_JITTER, BACKOFF_JITTER)))


def classify_error(exc) -> str:
    """把不同 HTTP 库的异常归一成我们自己的错误码（requests / curl_cffi 都要认）。"""
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timed out" in text:
        return "timeout"
    if "redirect" in name:
        return "too_many_redirects"
    if "ssl" in name or "certificate" in text:
        return "ssl_error"
    return "conn_error"


def close_response(resp) -> None:
    try:
        resp.close()
    except Exception:
        pass


def fetch_with_retry(session, url, *, allow_redirects=True, referer=None, stream=False,
                     tiers=None):
    """带指数退避的 GET，返回 (响应, 错误码)。

    退避只对「可能马上就好」的失败生效：超时、连接被掐、
    以及 403 / 408 / 412 / 429 / 5xx 这些限流与网关抖动。
    404 / 400 是站点明确说「没有」，立刻返回，不白等 50 秒。

    `tiers` 覆盖退避级数（默认 BACKOFF_TIERS=3）。[阶段 2.5] 的慢节奏复检传 0：
    那一轮的意义只是「风暴过去之后再问一次」，不是「再退避着重试三遍」。
    ★ 这是个真踩过的坑：加了逐请求退避之后忘了收口复检那一轮，于是每个失败域名
      被退避两次，而那一轮只有 4 个线程 —— update.py 从 26.8 分钟涨到 44 分钟
      还没跑完。
    """
    tiers = BACKOFF_TIERS if tiers is None else tiers
    headers = {"Referer": referer} if referer else None
    last_err = ""

    for attempt in range(tiers + 1):
        if attempt:
            sleep_backoff(attempt - 1)

        try:
            r = session.get(
                url,
                timeout=HTTP_TIMEOUT,
                allow_redirects=allow_redirects,
                verify=False,
                headers=headers or None,
                stream=stream,
            )
        except Exception as exc:
            last_err = classify_error(exc)
            continue

        # 还能再试，且这次是「临时性」失败 -> 关掉响应、退避后重来
        if r.status_code in TRANSIENT_STATUS and attempt < tiers:
            last_err = f"http_{r.status_code}"
            close_response(r)
            continue

        return r, None

    return None, last_err


def body_chunks(resp, size: int = 8192):
    """统一 requests / curl_cffi 的流式读取。"""
    if hasattr(resp, "iter_content"):
        for chunk in resp.iter_content(size):
            if chunk:
                yield chunk
        return
    data = resp.content or b""          # pragma: no cover - curl_cffi 没有 iter_content 时的兜底
    for i in range(0, len(data), size):
        yield data[i:i + size]


# ==================== 响应解码 ====================
_CT_CHARSET_RE = re.compile(r"charset\s*=\s*['\"]?([\w-]+)", re.I)
_META_CHARSET_RE = re.compile(
    r'<meta[^>]+charset\s*=\s*["\']?([\w-]+)', re.I
)


def response_text(resp) -> str:
    """把响应体解成 str。

    requests 在没有任何 charset 信息时会退回 ISO-8859-1，
    中文站点就会整页变成乱码（正则也就抓不到跳转地址了）。
    这里按 HTTP 头 -> <meta charset> -> apparent_encoding -> UTF-8 逐级兜底。
    """
    raw = resp.content

    m = _CT_CHARSET_RE.search(resp.headers.get("Content-Type", ""))
    if m:
        try:
            return raw.decode(m.group(1), errors="replace")
        except LookupError:
            pass

    head = raw[:4096].decode("ascii", errors="ignore")
    m = _META_CHARSET_RE.search(head)
    if m:
        try:
            return raw.decode(m.group(1), errors="replace")
        except LookupError:
            pass

    enc = getattr(resp, "apparent_encoding", None) or "utf-8"
    try:
        return raw.decode(enc, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


# ==================== 阶段 1：DNS ====================
def dns_lookup(item):
    u, a = item
    resolver = get_resolver()
    ips = []
    for attempt in range(DNS_ATTEMPTS):
        try:
            ips = [str(x) for x in resolver.resolve(a, "A")]
            break
        except dns.resolver.NXDOMAIN:
            # 域名确实不存在，重试没有意义
            break
        except Exception:
            ips = []
            # 换个服务器顺序再试一次（dnspython 不会自己重试失败的那一轮）
            resolver.nameservers = DNS_SERVERS[attempt + 1:] + DNS_SERVERS[:attempt + 1]
    return {"domain": u, "ascii": a, "ips": ips}


# ==================== 噪声 URL 过滤 ====================
NOISE_HOSTS = {
    "www.w3.org", "w3.org",
    "www.w3.com", "w3.com",
    "schemas.android.com",
    "ns.adobe.com",
    "purl.org",
    "xmlns.com",
    "ogp.me",
}

NOISE_PATH_HINTS = (
    "/2000/svg",
    "/1999/xlink",
    "/1999/xhtml",
    "/2000/xmlns",
    "/TR/",
)


def is_noise_url(u: str) -> bool:
    try:
        p = urlparse(u)
    except Exception:
        return True
    host = p.netloc.lower()
    if host in NOISE_HOSTS or host.endswith(".w3.org") or host.endswith(".w3.com"):
        return True
    path = p.path.lower()
    if any(h in path for h in NOISE_PATH_HINTS):
        return True
    return False


# ==================== HTML 明文跳转解析 ====================
META_RE = re.compile(
    r'<meta[^>]+http-equiv\s*=\s*["\']?refresh["\']?[^>]*'
    r'content\s*=\s*["\']?\s*\d+\s*;\s*url\s*=\s*([^"\'>\s]+)',
    re.I,
)

JS_LOC_RE = re.compile(
    r'(?:window\.)?location'
    r'(?:\s*\.\s*(?:href|replace|assign)\s*(?:=|\())?'
    r'\s*["\']([^"\']+)["\']',
    re.I,
)

SCRIPT_RE = re.compile(r"(?is)<script[^>]*>(.*?)</script>")

JS_CTX_URL_RE = re.compile(
    r'location[^;\n]{0,200}?(https?://[^\s"\'<>()\\]+)',
    re.I,
)

# ★ 「配置对象 + location.href = config.url」型模板：
#   var cfg = { url: 'http://www.example.edu.cn/', ... };
#   function go() { location.href = config.url; }      <- 这里没有字面量 URL
#   URL 出现在赋值语句里而不是 location 后面，所以上面两条正则都抓不到。
JS_CONFIG_RE = re.compile(
    r'["\']?(?:url|href|target|link|redirect|redirecturl|to|jump|jumpurl|site|home)["\']?'
    r'\s*[:=]\s*["\'](https?://[^"\']+)["\']',
    re.I,
)


# ---------- HTML body 里的目标域名（如 .edu.cn） ----------
BODY_TARGET_SUFFIXES = (".edu.cn",)
_BODY_SUFFIX_ALT = "|".join(re.escape(s.lstrip(".")) for s in BODY_TARGET_SUFFIXES)

BODY_TARGET_RE = re.compile(
    rf'(?:https?:)?//(?:[a-zA-Z0-9-]+\.)+(?:{_BODY_SUFFIX_ALT})(?::\d+)?'
    rf'(?:[/?#][^\s"\'<>()\\]*)?'
    rf'|'
    rf'(?<![\w.-])(?:[a-zA-Z0-9-]+\.)+(?:{_BODY_SUFFIX_ALT})(?::\d+)?'
    rf'(?:[/?#][^\s"\'<>()\\]*)?',
    re.I,
)


# ★ 判断一个 host 是否已经在目标后缀上（如已经是 xxx.edu.cn）
def has_target_suffix(host: str) -> bool:
    if not host:
        return False
    host = host.lower().split(":")[0]
    return any(
        host == s.lstrip(".") or host.endswith(s)
        for s in BODY_TARGET_SUFFIXES
    )


def extract_body_target(html: str, base: str):
    """在 HTML body 里查找 .edu.cn 之类的目标域名。

    只取根网址（scheme://host/），路径/query/fragment 全部丢弃。
    返回 (root_url, "body_target") 或 (None, None)。
    """
    html = html[:MAX_HTML]
    seen_hosts = set()

    for m in BODY_TARGET_RE.finditer(html):
        raw = m.group(0).strip()
        if not raw:
            continue

        if raw.startswith("//"):
            probe = "http:" + raw
        elif raw.startswith(("http://", "https://")):
            probe = raw
        else:
            probe = "http://" + raw

        try:
            p = urlparse(probe)
        except Exception:
            continue

        host = (p.netloc or "").lower()
        if not host:
            continue
        hostname = host.split(":")[0]
        if not hostname:
            continue

        if not any(hostname.endswith(s) for s in BODY_TARGET_SUFFIXES):
            continue

        if hostname in seen_hosts:
            continue
        seen_hosts.add(hostname)

        scheme = p.scheme if p.scheme in ("http", "https") else "https"
        root_url = f"{scheme}://{host}/"
        if is_noise_url(root_url):
            continue

        return root_url, "body_target"

    return None, None


# 静态资源后缀：从页面里"抢"出来的这些地址不是跳转目标，是外链的 CSS/字体/图片。
_STATIC_ASSET_RE = re.compile(
    r"\.(?:css|less|scss|sass|js|mjs|map|json|xml|png|jpe?g|gif|svg|webp|avif|"
    r"ico|bmp|woff2?|ttf|eot|otf|mp4|webm|mp3|wav)$",
    re.I,
)
# 解 URL 编码后还带这些字符的，八成是把 HTML 片段/模板当成了地址
_BAD_URL_CHARS = re.compile(r"""[<>"'`{}\\]""")


def is_sane_url(u: str) -> bool:
    """这个地址像不像一个「能访问的网页」？

    ★ 为什么需要：`location` 附近的 URL 是用正则在**可能已经损坏的 HTML** 里
      抠出来的，抠到过这种东西：
        https://www.hkust-gz.edu.cn/%3ELocation%3C/a%3E%3C/li%3E...
        https://www.polyu.edu.hk/:%20%7B%20%20%20...
      前者解码后是 `>Location</a></li>`，后者是 `: {    `。
      跟着它们走只会得到 404，还会把 final_url 污染成一串乱码。
    """
    if not u or not u.startswith(("http://", "https://")):
        return False
    # 原文里的空白（正则是按非空白截断的，出现空白说明是拼出来的）
    if any(c.isspace() for c in u):
        return False
    # 解码后再看一遍：编码过的尖括号 / 花括号同样是拼接痕迹
    if _BAD_URL_CHARS.search(unquote(u)):
        return False
    if _STATIC_ASSET_RE.search(urlparse(u).path):
        return False
    return True


def extract_next(html: str, base: str):
    html = html[:MAX_HTML]

    def ok(u: str) -> bool:
        return bool(u) and not is_noise_url(u) and is_sane_url(u)

    # 1) meta refresh
    m = META_RE.search(html)
    if m:
        u = urljoin(base, m.group(1))
        if ok(u):
            return u, "meta"

    # 2) window.location / location.href = ...
    for m in JS_LOC_RE.finditer(html):
        raw = m.group(1)
        if raw.startswith(("javascript:", "#", "about:")):
            continue
        u = urljoin(base, raw)
        if ok(u):
            return u, "js_location"

    # 3) script 里出现 location 附近拼的 URL
    for m in SCRIPT_RE.finditer(html):
        s = m.group(1)
        if "location" not in s:
            continue
        for raw in JS_CTX_URL_RE.findall(s):
            u = urljoin(base, raw)
            if ok(u):
                return u, "js_script"

    # 4) 配置对象里的字面量 URL（url: '...' / redirect: '...'）
    #    ★ 只扫 <script> 里的内容。
    #      以前直接扫整个 HTML，于是 `<link href="https://fonts.googleapis.com/...">`
    #      这种静态资源引用也被当成「跳转目标」—— 实测有域名被跳到
    #      fonts.googleapis.com 的字体 CSS 和 cdn.amoe.cc 的 misans.css 上。
    #      这个模式本来就只在 JS 配置对象里成立，扫 script 才是正确的作用域。
    #    ★ 跳过指向自己的（很多站点会在 og:url / canonical 里写自身地址）
    base_host = urlparse(base).netloc.lower()
    for sm in SCRIPT_RE.finditer(html):
        for m in JS_CONFIG_RE.finditer(sm.group(1)):
            raw = m.group(1)
            u = urljoin(base, raw)
            if not ok(u):
                continue
            if urlparse(u).netloc.lower() == base_host:
                continue
            return u, "js_config"

    # 5) 兜底：HTML body 里出现 .edu.cn 之类的目标域名
    u, how = extract_body_target(html, base)
    if u and ok(u):
        return u, how

    return None, None


# ==================== 这一跳该不该跟 ====================
# ★ 已知的「中间页 / 拦截页」。
#   域名跳到这些地方，说明这个奶龙域名并没有指向自己的校园站点，只是被停放、
#   被拦截、或者被甩给了搜索引擎。以前爬虫会继续跟着这些页面往下跳，于是抓回来
#   的标题变成「百度搜索结果」「DNSPod 的广告」「IE 下载帮助页」——
#   那已经是别人家网站的内部导航了。
INTERSTITIAL_HOSTS = {
    "dnspod.qcloud.com": "域名被 DNSPod 拦截（未解析或已封停）",
    "www.dnspod.cn": "域名被 DNSPod 拦截（未解析或已封停）",
    "support.microsoft.com": "落地页只认旧版 IE，被甩到浏览器下载说明页",
    "baidu.com": "域名被停放，跳到了百度",
    "www.baidu.com": "域名被停放，跳到了百度",
    "top.baidu.com": "域名被停放，跳到了百度",
    "m.baidu.com": "域名被停放，跳到了百度",
    "www.google.com": "域名被停放，跳到了 Google",
    "www.aliyun.com": "域名被停放，跳到了阿里云",
    "wanwang.aliyun.com": "域名被停放，跳到了阿里云",
}

# 「弱跳转信号」：页面里出现一个 `url: "..."` / 正文里出现一个 .edu.cn 域名，
# 都不代表「本站在跳转」。只有当它出现在这个奶龙域名自己的页面上时才认。
WEAK_JUMP_METHODS = ("body_target", "js_config")


def host_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().split(":")[0]
    except Exception:
        return ""


def interstitial_reason(url: str):
    """这个 URL 是不是已知的中间页？是的话返回一句人话，否则 None。"""
    host = host_of(url)
    if not host:
        return None
    if host in INTERSTITIAL_HOSTS:
        return INTERSTITIAL_HOSTS[host]
    for known, reason in INTERSTITIAL_HOSTS.items():
        if host.endswith("." + known):
            return reason
    return None


def should_follow(nxt: str, how: str, cur_url: str, origin_url: str) -> bool:
    """这一跳还该不该跟下去？纯函数，方便单测。

    三种「不该跟」：
      1. 当前已经站在中间页 / 拦截页上 —— 再往下是别人家网站的内部导航；
      2. 弱信号，且已经不在最初那个奶龙域名上 —— 典型事故：沈阳奶蛙大学.work
         落到某校教务系统，系统提示「请用 IE 打开」，页面里的
         `url: '...internet-explorer-downloads'` 被当成了跳转目标；
      3. 弱信号，且当前已经在 .edu.cn 上 —— 别被拖进 IAM / SSO 认证链。
    """
    if not nxt:
        return False

    if interstitial_reason(cur_url):
        return False

    if how in WEAK_JUMP_METHODS:
        cur_host = host_of(cur_url)
        if cur_host != host_of(origin_url):
            return False
        if has_target_suffix(cur_host):
            return False

    return True


# ==================== 阶段 2：HTTP + 跳转 ====================
def fetch_chain(session, url, allow_redirects=True, referer=None, tiers=None):
    """★ 支持传入 Referer；临时性失败会按指数退避重试（见 fetch_with_retry）。"""
    return fetch_with_retry(
        session, url, allow_redirects=allow_redirects, referer=referer, tiers=tiers,
    )


def http_check(item, delay=0.0, tiers=None):
    # 复检时用：错开每个线程发出的时间，别又攒成一波打过去
    if delay:
        time.sleep(random.uniform(0, delay))

    u, a, ips = item["domain"], item["ascii"], item["ips"]

    row = {
        "domain": u,
        "ascii": a,
        "ips": ips,
        "first_status": "",
        "final_url": "",
        "final_status": "",
        "redirect_chain": "",
        "latency_s": "",
        "method": "",
        "error": "",
        "_hop_count": 0,
    }

    if not ips:
        row["error"] = "no_dns"
        return row

    session = get_session()
    # ★ 每个域名随机挑一个 UA（同域名后续请求都用它）
    session.headers["User-Agent"] = random.choice(USER_AGENTS)

    start = time.perf_counter()

    hops = []
    methods = []
    err = ""

    url = f"https://{a}/"
    r, err = fetch_chain(session, url, allow_redirects=True, tiers=tiers)

    if r is None and err:
        url = f"http://{a}/"
        r, err = fetch_chain(session, url, allow_redirects=True, tiers=tiers)
        methods.append("http_fallback")

    if r is None:
        row["error"] = err
        row["latency_s"] = f"{time.perf_counter() - start:.3f}"
        return row

    for h in r.history:
        hops.append((h.status_code, h.url))
    hops.append((r.status_code, r.url))
    methods.append("requests")

    last_url = r.url
    visited = {last_url}
    origin_url = hops[0][1]

    for _ in range(MAX_HOPS):
        nxt, how = extract_next(response_text(r), last_url)
        if not nxt or nxt == last_url or nxt in visited:
            break

        # ★ 该不该跟这一跳，全部交给 should_follow（判断依据见上面那段注释）：
        #   已经站在中间页上就停；弱信号只在最初那个奶龙域名自己的页面上才认。
        if not should_follow(nxt, how, last_url, origin_url):
            break

        # ★ 明文跳转时把上一跳当作 Referer
        r, err = fetch_chain(session, nxt, allow_redirects=True, referer=last_url, tiers=tiers)
        if r is None:
            row["error"] = err
            break

        for h in r.history:
            hops.append((h.status_code, h.url))
        hops.append((r.status_code, r.url))
        methods.append(how)

        last_url = r.url
        visited.add(last_url)

        if len(hops) >= MAX_HOPS:
            break

    row["redirect_chain"] = " -> ".join(f"{st}:{u}" for st, u in hops)

    # ★ 落点如果还是中间页 / 拦截页，就把链接收回「最后一跳干净的地方」并打上
    #   blocked 标记 —— 后面既不抓标题也不下载校徽（那是别人家的页面）。
    reason = interstitial_reason(hops[-1][1])
    if reason:
        row["blocked"] = reason
        hops = [(st, u) for st, u in hops if not interstitial_reason(u)]

    if hops:
        row["first_status"] = hops[0][0]
        row["final_url"] = hops[-1][1]
        row["final_status"] = hops[-1][0]
    row["method"] = "+".join(dict.fromkeys(methods))
    row["latency_s"] = f"{time.perf_counter() - start:.3f}"
    row["_hop_count"] = len(hops)
    return row


def jump_type(method_str: str, hop_count: int) -> str:
    """direct / delayed / none"""
    if any(k in method_str for k in (
        "meta", "js_location", "js_script", "js_config", "body_target",
    )):
        return "delayed"
    if hop_count > 1:
        return "direct"
    return "none"


# ==================== 阶段 3：title + logo ====================
def score_image(img) -> int:
    """按 src/alt/class/id 里是否含 logo/icon 打分。"""
    parts = []
    for attr in ("src", "data-src", "data-original", "alt", "title", "class", "id"):
        v = img.get(attr)
        if not v:
            continue
        if isinstance(v, list):
            v = " ".join(v)
        parts.append(str(v).lower())
    text = " ".join(parts)
    if "logo" in text:
        return 2
    if "icon" in text:
        return 1
    return 0


def extract_title_logo(session, url, referer=None):
    """返回 (title, logo_url, err)。★ 支持 Referer；临时性失败走指数退避重试。"""
    r, err = fetch_with_retry(session, url, allow_redirects=True, referer=referer)
    if r is None:
        return "", "", err

    if r.status_code >= 400:
        return "", "", f"http_{r.status_code}"

    html = response_text(r)
    if len(html) > MAX_HTML_BODY:
        html = html[:MAX_HTML_BODY]

    soup = BeautifulSoup(html, "html.parser")

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    best_src, best_score = "", 0
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        if not src or not isinstance(src, str):
            continue
        if src.startswith(("data:", "javascript:", "about:", "#")):
            continue

        src_l = src.lower()
        if "favicon" in src_l:
            continue

        score = score_image(img)
        if "logo" in src_l:
            score = max(score, 2)
        elif "icon" in src_l and score == 0:
            score = 1

        if score > best_score:
            best_score, best_src = score, src

    logo_url = urljoin(r.url, best_src) if best_src else ""
    return title, logo_url, ""


def sniff_image_ext(head: bytes) -> str:
    """按魔数判断真实图片类型。

    ★ 不能信 Content-Type：很多站点在图片 404/403 时返回一个 200 的 HTML 报错页，
      按头的类型存下来就会得到一张「内容是 HTML 的 .img 校徽」。
    """
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    if head[:4] == b"\x00\x00\x01\x00":
        return ".ico"
    if head[:2] == b"BM":
        return ".bmp"
    stripped = head.lstrip()[:5].lower()
    if stripped.startswith(b"<svg") or stripped.startswith(b"<?xml"):
        return ".svg"
    return ""


def download_logo(session, url, out_dir, name, referer=None) -> str:
    """下载到 out_dir/name.ext，返回本地路径（失败返回空串）。★ 支持 Referer。"""
    if not url:
        return ""

    r, _err = fetch_with_retry(
        session, url, allow_redirects=True, referer=referer, stream=True,
    )
    if r is None:
        return ""

    # ★ 用 try/finally 关响应，注意**不能**写 `with r:`：
    #   requests 的 Response 支持上下文管理器，curl_cffi 的不支持
    #   （会直接 TypeError: 'Response' object does not support the context
    #   manager protocol）。早退不关连接会一直占着连接池，几十个线程很快就
    #   全部阻塞在 session.get() 上，整个抓取看起来像卡死。
    path = ""
    try:
        if r.status_code >= 400:
            return ""

        chunks = body_chunks(r)
        try:
            first = next(chunks)
        except StopIteration:
            return ""
        if not first:
            return ""

        # ★ 按魔数确认这真的是图片；不是就丢掉（见 sniff_image_ext 的说明）
        ext = sniff_image_ext(bytes(first[:64]))
        if not ext:
            return ""

        path = os.path.join(out_dir, f"{name}{ext}")
        written = 0
        too_big = False
        with open(path, "wb") as fh:
            for chunk in chain((first,), chunks):
                if not chunk:
                    continue
                written += len(chunk)
                if written > MAX_LOGO_BYTES:
                    too_big = True
                    break
                fh.write(chunk)
        if too_big:
            os.remove(path)
            return ""
    except Exception:
        # 半截文件不能留：prune_logos 只按 result.json 引用与否来清，
        # 这里不主动删的话会留下一个坏图。
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        return ""
    finally:
        close_response(r)

    if os.path.getsize(path) < MIN_LOGO_BYTES:
        try:
            os.remove(path)
        except OSError:
            pass
        return ""

    return path


# ==================== 校徽：按「重定向后的域名」去重 ====================
# ★ 为什么按落地域名而不是奶龙域名命名：
#   十几个奶龙域名常常指向同一所大学，用奶龙域名当文件名会把**同一张校徽
#   下载并保存十几遍**（请求数和仓库体积都是白花的）。改成用落地域名
#   （www.lnu.edu.cn）当 key，一所学校天然只有一份校徽。
_LOGO_BY_KEY = {}
_LOGO_LOCKS = {}
_LOGO_LOCKS_GUARD = threading.Lock()


def _key_lock(key: str) -> threading.Lock:
    with _LOGO_LOCKS_GUARD:
        lock = _LOGO_LOCKS.get(key)
        if lock is None:
            lock = _LOGO_LOCKS[key] = threading.Lock()
    return lock


def logo_key(url: str) -> str:
    """把落地 URL 变成校徽文件名（也就是落地域名）。

    ★ 必须是纯函数：指向同一所大学的所有奶龙域名都要算出同一个 key，
      否则「同一个域名不重复保存」就无从谈起。
    """
    host = host_of(url)
    if not host:
        return ""
    try:
        host = idna.encode(host).decode("ascii")
    except idna.IDNAError:
        pass
    safe = re.sub(r"[^a-z0-9.-]", "_", host.lower()).strip(".")
    if len(safe) > 80:      # 超长域名：截断 + 指纹，保证唯一又不撞文件名长度上限
        safe = f"{safe[:60]}-{hashlib.sha1(safe.encode()).hexdigest()[:16]}"
    return safe


def resolve_logo(session, url, key, referer=None) -> str:
    """下载校徽，按落地域名去重：同一个学校只下一次、只存一份。"""
    if not url or not key:
        return ""
    # 同一个落地域名的下载串行化：避免多个线程同时往同一个文件里写
    with _key_lock(key):
        cached = _LOGO_BY_KEY.get(key)
        if cached and os.path.isfile(cached):
            return cached
        path = download_logo(session, url, LOGO_DIR, key, referer=referer)
        if path:
            _LOGO_BY_KEY[key] = path
        return path


def enrich(item):
    """在 http_check 输出上补 title / logo / jump_type。"""
    row = dict(item)
    row["jump_type"] = jump_type(row.get("method", ""), row.get("_hop_count", 0))
    row["title"] = ""
    row["logo_url"] = ""
    row["logo_path"] = ""

    final_url = row.get("final_url") or ""
    if not final_url or row.get("error"):
        row.pop("_hop_count", None)
        return row

    # 落到中间页 / 拦截页的域名：链接已经收回奶龙域名本身，这时候再去抓标题、
    # 校徽只会抓到别人家的页面（百度搜索结果、DNSPod 广告……），直接跳过。
    if row.get("blocked"):
        row.pop("_hop_count", None)
        return row

    session = get_session()
    # ★ 抓取最终页时把 final_url 自身当 Referer
    title, logo_url, err = extract_title_logo(session, final_url, referer=final_url)
    if err and not row.get("error"):
        row["error"] = f"page:{err}"

    row["title"] = title
    row["logo_url"] = logo_url

    if logo_url:
        # ★ 下载 logo 时用最终页 URL 作 Referer，并按「重定向后的域名」存
        row["logo_path"] = resolve_logo(
            session, logo_url, logo_key(final_url), referer=final_url,
        )

    row.pop("_hop_count", None)
    return row


# ==================== 输出 ====================
JSON_FIELDS = [
    "domain", "ascii", "final_url", "title",
    "logo_path", "logo_url",
    "jump_type", "redirect_chain", "method",
    "first_status", "final_status", "latency_s", "ips", "error",
    "blocked",
    # 历史保留用：第一次失联的日期 / 最后一次访问成功的日期
    "down_since", "last_ok",
    # 来源：空串=模板域名，community=网友投稿（会带一个「网友投稿」徽章）
    "source",
]


def write_json(path, rows):
    out = []
    for r in rows:
        item = {k: r.get(k, "") for k in JSON_FIELDS}
        if isinstance(item["ips"], list):
            item["ips"] = ",".join(item["ips"])
        out.append(item)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def load_previous_ips(path):
    """上一轮 result.json 里「域名 -> IP」的对照表。"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            rows = json.load(fh)
    except Exception:
        return {}
    out = {}
    for row in rows:
        if isinstance(row, dict) and row.get("ascii"):
            out[row["ascii"]] = row.get("ips", "")
    return out


def load_previous_rows(path):
    """上一轮 result.json 的全部行，用于历史合并。"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            rows = json.load(fh)
    except Exception:
        return []
    return rows if isinstance(rows, list) else []


# ==================== 历史保留：失联不立刻删 ====================
def parse_date(value):
    """把 'YYYY-MM-DD'（或更长的 ISO 串）解析成 date；解析不了返回 None。"""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def is_up(row) -> bool:
    """这一轮算不算「访问到了」。

    ★ 口径必须和前端 build-data.mjs 里的 statusBadgeOf() 一致：只看 HTTP 终态码
      2xx/3xx，且落点不是中间页/拦截页。不一致就会出怪事 ——
      卡片上写着「可访问」，却因为被判失联而从墙上消失。
    """
    if row.get("blocked"):
        return False
    code = row.get("final_status")
    return isinstance(code, int) and 200 <= code < 400


# ==================== 网友投稿的审核落地 ====================
def _reject_reason(row) -> str:
    if row.get("blocked"):
        return f"落到了中间页 / 拦截页：{row['blocked']}"
    status = row.get("final_status")
    if isinstance(status, int):
        return f"HTTP {status}，拿不到有效落点"
    return f"抓取失败：{row.get('error') or '没有任何响应'}"


def apply_reviews(rows, store, today):
    """用抓取结果更新投稿状态，并且**只保留已通过的投稿行**。

    ★ 为什么必须等抓完才判：投稿那一刻根本不知道这个域名会跳到哪儿。
      判据见 community.classify_landing —— 只有落点在**受限教育域名**上才自动
      通过（.edu.cn / .edu / .ac.uk 这类是注册受管制的，投毒者买不到）；
      落点不是教育的保持 pending 等人工加 approved 标签，而不是自动拒 ——
      因为 www.gdut.cn 这种真实大学也用非教育域名。

    ★ 未通过的行会被丢掉，于是 result.json 里不再引用它，
      prune_logos.py 下一轮就会顺手删掉它的校徽 —— 没通过审核的投稿
      不会把图片留在仓库里。

    返回 (留下的行, 更新后的 store, 状态变化列表)。
    """
    entries = {e.get("ascii"): e for e in store.get("domains", [])}
    changes, kept = [], []

    for row in rows:
        ascii_ = row.get("ascii") or ""
        entry = entries.get(ascii_)

        # 模板域名：原样保留
        if entry is None:
            kept.append(row)
            continue

        row = dict(row)
        row["source"] = "community"      # 前端据此显示「网友投稿」徽章
        status = entry.get("status")

        if status == "approved":
            # 已经通过的：保持通过；真失联了交给 merge_history 的 3 天宽限期
            kept.append(row)
        elif status == "rejected":
            # 已经否掉的：不该再出现在这一轮里（除非有人手改了 JSON）
            continue
        else:
            decision = classify_landing(row, entry.get("reported_at"), today)
            if decision == "approve":
                entry["status"] = "approved"
                entry["approved_at"] = today.isoformat()
                entry["note"] = "落点在受限教育域名上，自动通过"
                changes.append((ascii_, "approved", entry["note"]))
                kept.append(row)
            elif decision == "reject":
                entry["status"] = "rejected"
                entry["note"] = _reject_reason(row)
                changes.append((ascii_, "rejected", entry["note"]))
                # 不保留：result.json 不再引用它，prune_logos.py 下一轮清掉校徽
            else:
                changes.append((
                    ascii_, "pending",
                    f"还没有效落点（HTTP {row.get('final_status') or '—'}），等下一轮",
                ))

    return kept, store, changes


def merge_history(rows, previous, today):
    """把这一轮结果和历史合并：失联不立刻删，连续失联满 RETENTION_DAYS 天才移除。

    ★ 为什么不删：偶发的网络抖动、对端限流、公共 DNS 丢包都会让某天抓不到，
      直接删的话卡片会每天在墙上忽隐忽现。现在先降级成「打不开」继续挂着，
      连着几天都回不来才真的移除。

    规则：
      · 本轮通了   -> 清空 down_since，刷新 last_ok；
      · 本轮没通   -> 沿用历史里的 down_since（没有就记今天），并把历史里的
                      title / logo / final_url 带过来：卡片降级但内容不空白；
      · 从没记录过又没通 -> 直接跳过（否则 5 万多个候选域名会在第一次运行时
                            被全部写进 result.json）；
      · 连续失联满 RETENTION_DAYS 天 -> 移除。

    返回 (保留的行, 被移除的域名列表)。
    """
    prev = {
        r["ascii"]: r for r in previous
        if isinstance(r, dict) and r.get("ascii")
    }
    today_s = today.isoformat()
    kept, retired = [], []
    seen = set()

    for row in rows:
        key = row.get("ascii") or ""
        seen.add(key)
        old = prev.get(key) or {}
        row = dict(row)

        if is_up(row):
            row["down_since"] = ""
            row["last_ok"] = today_s
            kept.append(row)
            continue

        if not old:
            continue

        row["down_since"] = old.get("down_since") or today_s
        row["last_ok"] = old.get("last_ok", "")
        for field in ("title", "logo_url", "logo_path", "final_url"):
            if not row.get(field):
                row[field] = old.get(field, "")

        since = parse_date(row["down_since"])
        if since and (today - since).days >= RETENTION_DAYS:
            retired.append(row.get("domain") or key)
            continue
        kept.append(row)

    # 历史里有、这一轮连候选名单都没进的（词表改过之类）：同样按宽限期处理
    for key, old in prev.items():
        if key in seen:
            continue
        since = parse_date(old.get("down_since")) or today
        if (today - since).days >= RETENTION_DAYS:
            retired.append(old.get("domain") or key)
            continue
        carried = dict(old)
        carried["down_since"] = since.isoformat()
        kept.append(carried)

    return kept, retired


def rescue_dns(item, previous_ips):
    """对「上一轮有记录、这一轮没查到」的域名做一次更有耐心的复检。

    ★ 为什么需要：5 万次查询的高并发会偶发触发公共 DNS 的限流/丢包，
      而这些域名本身是活的。不复检的话，每天的收录数量会在 120~165 之间来回跳，
      页面上的卡片会莫名其妙地消失又出现。
    """
    u, a = item
    if not previous_ips.get(a):
        return {"domain": u, "ascii": a, "ips": []}

    resolver = dns.resolver.Resolver()
    resolver.nameservers = DNS_SERVERS
    resolver.timeout = DNS_RESCUE_TIMEOUT
    resolver.lifetime = DNS_RESCUE_LIFETIME
    try:
        ips = [str(x) for x in resolver.resolve(a, "A")]
    except Exception:
        ips = []
    return {"domain": u, "ascii": a, "ips": ips}


# ==================== 主流程 ====================
def is_transient(row) -> bool:
    """这一行是不是「像是被限流 / 超时」，值得换个节奏再问一遍？

    没有拿到状态码（超时、连接被掐）算临时失败；
    拿到了状态码则只有限流/网关抖动那一类才算。
    """
    if row.get("blocked"):
        return False
    code = row.get("final_status")
    if not isinstance(code, int):
        return True
    return code in TRANSIENT_STATUS


def main():
    os.makedirs(LOGO_DIR, exist_ok=True)

    targets = (
        build_targets(NAME_TREE_1, CN_TLDS, EN_TLDS)
        + build_targets(NAME_TREE_2, CN_TLDS, EN_TLDS)
    )

    # ---------- 并上网友投稿的「非模板域名」 ----------
    # ★ 投稿只是**候选**：这里只是把它塞进和其他 5 万多个域名完全一样的
    #   DNS → HTTP → 跳转解析流水线，不为它开任何后门。
    #   pending 的也要抓 —— 不抓就永远判不出落点，也就永远没法自动通过。
    store = load_community(COMMUNITY_JSON)
    template_ascii = {a for _u, a in targets}
    community_targets = [
        (u, a) for u, a in community_target_domains(store)
        if a not in template_ascii        # 模板已经覆盖的不用重复抓
    ]
    targets = targets + community_targets
    print(f"共 {len(targets)} 个域名（其中网友投稿 {len(community_targets)} 个）")

    print("\n[阶段 1] DNS 解析")
    dns_results = thread_map(
        dns_lookup, targets,
        max_workers=DNS_WORKERS, desc="DNS", chunksize=16,
    )

    # 补救：上一轮活着、本轮没查到的，换个节奏再查一遍
    previous_ips = load_previous_ips(OUT_JSON)
    n_dns = len([r for r in dns_results if r["ips"]])
    rescue_targets = [
        t for t, r in zip(targets, dns_results)
        if not r["ips"] and previous_ips.get(t[1])
    ]
    if rescue_targets:
        print(f"\n[阶段 1.5] 上一轮有记录但本轮没查到 {len(rescue_targets)} 个，复检中")
        rescued = thread_map(
            lambda t: rescue_dns(t, previous_ips), rescue_targets,
            max_workers=DNS_RESCUE_WORKERS, desc="DNS复检", chunksize=1,
        )
        by_ascii = {r["ascii"]: r for r in dns_results}
        for r in rescued:
            if r["ips"]:
                by_ascii[r["ascii"]]["ips"] = r["ips"]
        back = len([r for r in dns_results if r["ips"]]) - n_dns
        print(f"复检救回 {back} / {len(rescue_targets)} 个")

    live = [r for r in dns_results if r["ips"]]
    print(f"有 DNS 记录: {len(live)} / {len(targets)}")

    print("\n[阶段 2] HTTP 探测 + 跳转解析")
    http_results = thread_map(
        http_check, live,
        max_workers=HTTP_WORKERS, desc="HTTP", chunksize=1,
    )

    # 复检：高并发下被限流 / 网络抖掉的行，慢节奏再问一遍。
    # ★ 为什么需要：这些域名很多挂在同一个停放跳转服务后面，一波打过去会被
    #   限流成 403/412/429 或者直接断连 —— 不复检就会有一批活域名被标成
    #   「打不开」，而且每天的名单还会来回跳。
    # ★ tiers=0：这一轮**不再退避重试**。逐请求退避已经在阶段 2 用过了，
    #   在这里再退避三遍是重复的；而这一轮只有几个线程，重复退避会把整个抓取
    #   拖长一倍（实测 26.8 分钟 -> 44 分钟还没跑完）。
    #   这一轮的价值是「等风暴过去之后再问一次」，一次干净的单发就够。
    retry_targets = [r for r in http_results if is_transient(r)]
    if retry_targets:
        print(f"\n[阶段 2.5] {len(retry_targets)} 个疑似被限流 / 超时，降并发复检")
        retried = thread_map(
            lambda it: http_check(it, delay=HTTP_RETRY_JITTER, tiers=0), retry_targets,
            max_workers=HTTP_RETRY_WORKERS, desc="HTTP复检", chunksize=1,
        )
        by_ascii = {r["ascii"]: r for r in http_results}
        back = 0
        for r in retried:
            # 只有复检结果更好才替换，别把原来就好的行覆盖坏
            if not is_transient(r):
                by_ascii[r["ascii"]] = r
                back += 1
        print(f"复检救回 {back} / {len(retry_targets)} 个")
        http_results = [by_ascii[r["ascii"]] for r in http_results]

    print("\n[阶段 3] 抓取 title + logo")
    enriched = thread_map(
        enrich, http_results,
        max_workers=HTTP_WORKERS, desc="Page", chunksize=1,
    )

    dead = [{
        "domain": r["domain"], "ascii": r["ascii"], "ips": [],
        "first_status": "", "final_url": "", "final_status": "",
        "redirect_chain": "", "latency_s": "", "method": "",
        "title": "", "logo_url": "", "logo_path": "",
        "jump_type": "none", "error": "no_dns",
    } for r in dns_results if not r["ips"]]

    # ---------- 统计 ----------
    n_live = len(enriched)
    n_direct = sum(1 for r in enriched if r.get("jump_type") == "direct")
    n_delayed = sum(1 for r in enriched if r.get("jump_type") == "delayed")
    n_none = sum(1 for r in enriched if r.get("jump_type") == "none")
    n_jump = n_direct + n_delayed
    n_http_jump = n_direct

    n_no_title = sum(1 for r in enriched if not r.get("title"))
    n_no_logo_url = sum(1 for r in enriched if not r.get("logo_url"))
    n_no_logo_file = sum(1 for r in enriched if not r.get("logo_path"))
    n_has_title = n_live - n_no_title
    n_has_logo_file = n_live - n_no_logo_file

    print("\n[阶段 4] 统计")
    print(f"参与 HTTP 探测（有 DNS）: {n_live}")
    print(f"无 DNS 记录            : {len(dead)} / {len(targets)}")
    print(f"有跳转（含明文跳转）    : {n_jump}  "
          f"(HTTP 跳转 {n_http_jump} / 明文跳转 {n_delayed})")
    print(f"无跳转                 : {n_none}")
    print(f"抓到 title             : {n_has_title} / {n_live}"
          f"  （未抓到 {n_no_title}）")
    print(f"抓到 logo URL          : {n_live - n_no_logo_url} / {n_live}"
          f"  （未抓到 {n_no_logo_url}）")
    print(f"成功下载 logo 文件      : {n_has_logo_file} / {n_live}"
          f"  （未下载 {n_no_logo_file}）")

    # ---------- 网友投稿审核：pending 的按落点自动升/拒 ----------
    reviewed, store, review_changes = apply_reviews(
        enriched + dead, store, date.today(),
    )
    if review_changes:
        print("\n[阶段 3.5] 网友投稿审核")
        for ascii_, status, note in review_changes:
            print(f"  {ascii_} -> {status}：{note}")
    if community_targets:
        save_community(COMMUNITY_JSON, store)

    # ---------- 历史合并：失联不立刻删 ----------
    previous = load_previous_rows(OUT_JSON)
    merged, retired = merge_history(reviewed, previous, date.today())

    n_down_kept = sum(1 for r in merged if r.get("down_since"))
    n_community = sum(1 for r in merged if r.get("source") == "community")
    print(f"\n[阶段 4] 历史合并")
    print(f"收录（含失联未满 {RETENTION_DAYS} 天的历史卡片）: {len(merged)}")
    print(f"其中网友投稿          : {n_community}")
    print(f"其中失联保留          : {n_down_kept}")
    if retired:
        preview = ", ".join(retired[:6]) + (" …" if len(retired) > 6 else "")
        print(f"连续失联满 {RETENTION_DAYS} 天，移除: {len(retired)} 个（{preview}）")

    write_json(OUT_JSON, merged)
    print(f"\n完成，结果写入 {OUT_JSON}，logo 保存在 {LOGO_DIR}/")


if __name__ == "__main__":
    main()