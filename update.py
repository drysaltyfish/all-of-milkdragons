# check_domains.py
import json
import os
import re
import threading
import time
from itertools import product
from urllib.parse import urljoin, urlparse

import random
import idna
import dns.resolver
import requests
import urllib3
from bs4 import BeautifulSoup
from tqdm.contrib.concurrent import thread_map

from const import *

urllib3.disable_warnings()

# ---------- 配置 ----------
DNS_WORKERS = 500
HTTP_WORKERS = 200

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

OUT_JSON = "result.json"
LOGO_DIR = "logos"

MAX_HOPS = 5
MAX_HTML = 300_000_000_000
MAX_HTML_BODY = 2_000_000_000     # title/logo 解析用，可稍大
MIN_LOGO_BYTES = 64           # 太小的当失败


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
    """★ 用 const.py 里的完整浏览器头初始化 Session。"""
    if not hasattr(_tl, "session"):
        s = requests.Session()
        s.headers.update(DEFAULT_HEADERS)   # 完整 UA / Accept / Sec-Fetch-* 等
        s.max_redirects = MAX_HOPS
        _tl.session = s
    return _tl.session


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


def extract_next(html: str, base: str):
    html = html[:MAX_HTML]

    # 1) meta refresh
    m = META_RE.search(html)
    if m:
        u = urljoin(base, m.group(1))
        if not is_noise_url(u):
            return u, "meta"

    # 2) window.location / location.href = ...
    for m in JS_LOC_RE.finditer(html):
        raw = m.group(1)
        if raw.startswith(("javascript:", "#", "about:")):
            continue
        u = urljoin(base, raw)
        if not is_noise_url(u):
            return u, "js_location"

    # 3) script 里出现 location 附近拼的 URL
    for m in SCRIPT_RE.finditer(html):
        s = m.group(1)
        if "location" not in s:
            continue
        for raw in JS_CTX_URL_RE.findall(s):
            u = urljoin(base, raw)
            if not is_noise_url(u):
                return u, "js_script"

    # 4) 配置对象里的字面量 URL（url: '...' / redirect: '...'）
    #    跳过指向自己的（很多站点会在 og:url / canonical 里写自身地址）
    base_host = urlparse(base).netloc.lower()
    for m in JS_CONFIG_RE.finditer(html):
        raw = m.group(1)
        u = urljoin(base, raw)
        if is_noise_url(u):
            continue
        if urlparse(u).netloc.lower() == base_host:
            continue
        return u, "js_config"

    # 5) 兜底：HTML body 里出现 .edu.cn 之类的目标域名
    u, how = extract_body_target(html, base)
    if u:
        return u, how

    return None, None


# ==================== 阶段 2：HTTP + 跳转 ====================
def fetch_chain(session, url, allow_redirects=True, referer=None):
    """★ 支持传入 Referer。"""
    headers = {}
    if referer:
        headers["Referer"] = referer
    try:
        r = session.get(
            url,
            timeout=HTTP_TIMEOUT,
            allow_redirects=allow_redirects,
            verify=False,
            headers=headers or None,
        )
        return r, None
    except requests.exceptions.Timeout:
        return None, "timeout"
    except requests.exceptions.ConnectionError:
        return None, "conn_error"
    except requests.exceptions.TooManyRedirects:
        return None, "too_many_redirects"
    except Exception as e:
        return None, type(e).__name__


def http_check(item):
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
    r, err = fetch_chain(session, url, allow_redirects=True)

    if r is None and err:
        url = f"http://{a}/"
        r, err = fetch_chain(session, url, allow_redirects=True)
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

    for _ in range(MAX_HOPS):
        nxt, how = extract_next(response_text(r), last_url)
        if not nxt or nxt == last_url or nxt in visited:
            break

        # ★ 关键修复：当前页面已经在 .edu.cn 上时，不再因为 body_target / js_config
        #   这类"弱信号"继续深入跳转（避免被拖进 IAM / SSO 认证链，
        #   也避免把真实大学页面里的 url: '...' 当成跳转）。
        #   meta / js_location / js_script 这类"显式跳转"仍允许。
        if how in ("body_target", "js_config"):
            cur_host = urlparse(last_url).netloc.lower()
            if has_target_suffix(cur_host):
                break

        # ★ 明文跳转时把上一跳当作 Referer
        r, err = fetch_chain(session, nxt, allow_redirects=True, referer=last_url)
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

    row["first_status"] = hops[0][0]
    row["final_url"] = hops[-1][1]
    row["final_status"] = hops[-1][0]
    row["redirect_chain"] = " -> ".join(f"{st}:{u}" for st, u in hops)
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
    """返回 (title, logo_url, err)。★ 支持 Referer。"""
    headers = {"Referer": referer} if referer else None
    try:
        r = session.get(
            url,
            timeout=HTTP_TIMEOUT,
            verify=False,
            allow_redirects=True,
            headers=headers,
        )
    except Exception as e:
        return "", "", type(e).__name__

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
    headers = {"Referer": referer} if referer else None
    try:
        r = session.get(
            url,
            timeout=HTTP_TIMEOUT,
            verify=False,
            stream=True,
            allow_redirects=True,
            headers=headers,
        )
    except Exception:
        return ""

    # ★ 用 with 保证任何分支都会关掉流式响应。
    #   早退不关连接会一直占着 urllib3 的连接池，200 个线程很快就全部阻塞在
    #   session.get() 上，整个抓取看起来像卡死。
    with r:
        if r.status_code >= 400:
            return ""

        chunks = r.iter_content(8192)
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

        filename = f"{name}{ext}"
        path = os.path.join(out_dir, filename)

        try:
            with open(path, "wb") as f:
                f.write(first)
                for chunk in chunks:
                    if chunk:
                        f.write(chunk)
        except Exception:
            return ""

    if os.path.getsize(path) < MIN_LOGO_BYTES:
        try:
            os.remove(path)
        except OSError:
            pass
        return ""

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

    session = get_session()
    # ★ 抓取最终页时把 final_url 自身当 Referer
    title, logo_url, err = extract_title_logo(session, final_url, referer=final_url)
    if err and not row.get("error"):
        row["error"] = f"page:{err}"

    row["title"] = title
    row["logo_url"] = logo_url

    if logo_url:
        # ★ 下载 logo 时用最终页 URL 作 Referer
        row["logo_path"] = download_logo(
            session, logo_url, LOGO_DIR, row["ascii"], referer=final_url,
        )

    row.pop("_hop_count", None)
    return row


# ==================== 输出 ====================
JSON_FIELDS = [
    "domain", "ascii", "final_url", "title",
    "logo_path", "logo_url",
    "jump_type", "redirect_chain", "method",
    "first_status", "final_status", "latency_s", "ips", "error",
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
def main():
    os.makedirs(LOGO_DIR, exist_ok=True)

    targets = (
        build_targets(NAME_TREE_1, CN_TLDS, EN_TLDS)
        + build_targets(NAME_TREE_2, CN_TLDS, EN_TLDS)
    )
    print(f"共 {len(targets)} 个域名")

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

    write_json(OUT_JSON, enriched)
    print(f"\n完成，结果写入 {OUT_JSON}，logo 保存在 {LOGO_DIR}/")


if __name__ == "__main__":
    main()