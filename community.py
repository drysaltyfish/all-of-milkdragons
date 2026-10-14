#!/usr/bin/env python3
"""
网友投稿的「非模板域名」—— 规则、存储与审核判定。

只在 `community-domains.json` 里登记候选域名；**投稿内容永远不会直接进页面**。
一个投稿域名要变成卡片，必须：

    投稿 → pending 进候选池 → 下一次 update.py 抓取
         → 落点在受限教育域名上 → 自动 approved（见 classify_landing）
         → 落点不是           → 保持 pending，等人加 approved 标签
         → 抓不到 / 落到拦截页 → rejected
         → 只有 approved 的行才会被写进 result.json，进而上墙

这样即使有人批量投稿，也得先让域名真的跳到一所大学才能出现在页面上 ——
而受限教育域名（.edu.cn / .edu / .ac.uk …）是**注册受管制**的，
不是随便买一个就能用。这就是自动通过那一步的安全依据。

用法（被 update.py 与 triage_report.py 复用）：
    python3 -c "import community; print(community.load('community-domains.json'))"
"""
import json
import os
import re
import unicodedata
from datetime import date

import idna

STORE_PATH = "community-domains.json"
STORE_VERSION = 1

# ==================== 关键判据：受限教育域名 ====================
# ★ 这个列表就是「自动通过」的安全依据，往里加后缀是一个安全决策，不是配置调整。
#   入选标准：该后缀由**教育主管部门或认证机构**审核后才分配，普通人买不到。
#   （比如 .edu.cn 要 CNNIC 实名 + 办学资质；.edu 要 CHEA 认证；
#     .ac.uk 要 JISC 审核。）
EDU_SUFFIXES = (
    # 中国大陆
    ".edu.cn", ".ac.cn",
    # 美国 / 国际通用
    ".edu",
    # 港澳台
    ".edu.hk", ".edu.tw", ".edu.mo", ".ac.tw",
    # 亚太
    ".ac.jp", ".edu.sg", ".ac.kr", ".edu.au", ".ac.nz", ".edu.my", ".ac.in",
    # 欧洲
    ".ac.uk", ".edu.ie", ".ac.at", ".edu.pl",
)

# 不适合当「校园落地页」的后缀：短链、免费托管、博客平台。
# 这些域名即使某个时刻跳到了学校，落地页本身也不代表学校，而且极易被回收/转手。
DENY_SUFFIXES = (
    "bit.ly", "t.co", "tinyurl.com", "goo.gl", "is.gd", "cutt.ly", "shorturl.at",
    "github.io", "netlify.app", "vercel.app", "pages.dev", "workers.dev",
    "blogspot.com", "wordpress.com", "weebly.com", "wixsite.com",
    "bilibili.com", "space.bilibili.com", "weibo.com", "zhihu.com",
    "bytecdntp.com", "w7w5.55ip.top",
)

# 明确不给过的关键词（出现在域名标签里就拒）—— 只要最简单的一层，
# 真正的判据是「落点必须是教育域名」，这里只挡住明显不该挂在校园名录上的东西。
DENY_LABEL_KEYWORDS = (
    "porn", "sex", "xxx", "adult", "casino", "bet", "gambling", "viagra",
    "loan", "crypto", "btc", "pharm", "赌博", "色情", "博彩", "彩票", "代购", "刷单",
)

# 投稿配额：挡住「一个号一晚上灌几百条」
REPORT_DAILY_QUOTA = 5     # 同一账号 24 小时内最多投稿数
PENDING_CAP = 50           # 整个仓库同时处于 pending 的条数上限
COMMUNITY_CAP = 500        # 社区域名总数上限（approved + pending）
MIN_ACCOUNT_AGE_DAYS = 30  # 投稿账号的最小年龄，挡住一次性小号

# pending 超过这么多天还没被自动/人工通过，就判为 rejected（避免永远堆着）
REVIEW_GRACE_DAYS = 7

# 站点自己明确说「不存在」的状态码 -> 不用等宽限期，直接拒
DEFINITIVE_MISS_STATUS = {400, 404, 410, 451}

_DOMAIN_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")


# ==================== 归一化与校验（纯函数） ====================
def normalize(text) -> str:
    """把用户输入揉成裸域名。

    容忍这些写法：全角字符、`https://`、路径、查询串、端口、末尾点、`www.` 前缀。
    这一步只做「清洗」，合法与否交给 is_valid_domain。
    """
    if not isinstance(text, str):
        return ""
    s = unicodedata.normalize("NFKC", text).strip().lower()
    s = s.split("://", 1)[-1]          # 去协议
    s = s.split("/", 1)[0]             # 去路径
    s = s.split("?", 1)[0].split("#", 1)[0]
    s = s.split("@")[-1]               # 去 userinfo
    s = s.split(":", 1)[0]             # 去端口
    s = s.strip().strip(".")           # 去首尾点
    if s.startswith("www."):
        s = s[4:]
    return s


def to_ascii(domain: str) -> str:
    """转 punycode；转不了返回空串。"""
    if not domain:
        return ""
    try:
        return idna.encode(domain).decode("ascii")
    except idna.IDNAError:
        return ""


def is_valid_domain(domain: str) -> bool:
    """裸域名是否合法（此时应该是 normalize + 可选 punycode 之后的形式）。"""
    if not domain or len(domain) > 253:
        return False
    if ".." in domain or domain.startswith("-") or domain.endswith("-"):
        return False
    labels = domain.split(".")
    if len(labels) < 2:
        return False
    # 顶级标签不能是纯数字（挡掉 IP 字面量）
    if labels[-1].isdigit():
        return False
    for label in labels:
        if not label or len(label) > 63:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False
    return bool(_DOMAIN_RE.match(domain))


def denied_reason(domain: str) -> str:
    """命中黑名单就返回一句人话，否则空串。domain 应为 ASCII 形式。

    ★ ASCII 关键词按**整段**匹配（允许后面跟数字，如 casino888），不能直接用
      子串：`bet` 是 `bethel` 的子串，用子串会把 `bethel.edu.cn` 这种完全正常
      的教育域名误杀。宁可漏掉几个明显的赌博域名 —— 反正它们也过不了
      「落点必须是受限教育域名」那一关，会被人工拒掉。
    """
    d = domain.lower()
    for suffix in DENY_SUFFIXES:
        if d == suffix or d.endswith("." + suffix):
            return f"{suffix} 不适合作为校园落地页（短链 / 免费托管 / 内容平台）"

    tokens = [t for t in re.split(r"[.\-]", d) if t]
    for kw in DENY_LABEL_KEYWORDS:
        if kw.isascii():
            pattern = re.compile(re.escape(kw) + r"\d*")
            if any(pattern.fullmatch(tok) for tok in tokens):
                return f"域名里含关键词「{kw}」"
        elif kw in d:      # 中文关键词不会出现在正常词内部，子串匹配是安全的
            return f"域名里含关键词「{kw}」"
    return ""


# ==================== 落点判定 ====================
def host_of(url: str) -> str:
    """URL -> host（小写、无端口、无 userinfo）。"""
    if not isinstance(url, str) or not url:
        return ""
    s = url.split("://", 1)[-1]
    s = s.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    s = s.split("@")[-1].split(":")[0]
    return s.strip().lower()


def edu_landing(url: str) -> bool:
    """落点是不是**受限教育域名** —— 自动通过的唯一依据。

    ★ 注意不能用「落点以 .edu.cn 结尾」这种简化的写法来判断整个数据集：
      实测 191 个有落点的行里只有 143 个落在 .edu.cn，其余是
      www.gdut.cn / www.polyu.edu.hk / 裸 IP 教务系统 这类。
      所以这里只在**投稿域名**的自动通过上用受限教育后缀，
      非教育后缀的合法投稿走人工 approved 标签。
    """
    host = host_of(url)
    if not host:
        return False
    return any(host == s.lstrip(".") or host.endswith(s) for s in EDU_SUFFIXES)


def classify_landing(row, reported_at=None, today=None) -> str:
    """抓取结果 -> 审核决定：`approve` / `reject` / `wait`。纯函数，方便单测。

    保守优先：**只有落点确实在受限教育域名上才自动通过**，
    其余一律 `wait`（等人加 approved 标签），而不是自动拒 ——
    因为「落点不是 .edu.cn」既有可能是投毒，也有可能是
    www.gdut.cn 这种真实大学用了非教育域名。
    """
    if not row:
        return "reject"

    # 落到域名拦截页 / 停放页：对投稿域名来说等于没有价值
    if row.get("blocked"):
        return "reject"

    status = row.get("final_status")
    if not isinstance(status, int):
        # 没拿到状态码（超时 / 断连）：可能只是抖动，给宽限期
        return _overdue(reported_at, today) or "wait"

    if 200 <= status < 400:
        if edu_landing(row.get("final_url", "")):
            return "approve"
        return _overdue(reported_at, today) or "wait"

    if status in DEFINITIVE_MISS_STATUS:
        return "reject"

    # 403 / 412 / 429 / 5xx：多半是限流或源站抖动，等下一次
    return _overdue(reported_at, today) or "wait"


def _overdue(reported_at, today):
    """pending 超过 REVIEW_GRACE_DAYS 天还没通过 -> 判拒。"""
    if not reported_at or today is None:
        return None
    try:
        since = date.fromisoformat(str(reported_at)[:10])
    except ValueError:
        return None
    return "reject" if (today - since).days >= REVIEW_GRACE_DAYS else None


# ==================== 存储 ====================
def empty_store() -> dict:
    return {"version": STORE_VERSION, "domains": []}


def load(path: str = STORE_PATH) -> dict:
    if not os.path.exists(path):
        return empty_store()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return empty_store()
    if not isinstance(data, dict) or not isinstance(data.get("domains"), list):
        return empty_store()
    return data


def save(path: str, data: dict) -> None:
    data = dict(data)
    data["version"] = STORE_VERSION
    data["domains"] = sorted(data.get("domains", []), key=lambda e: e.get("ascii", ""))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def find(data: dict, ascii_domain: str):
    """按 punycode 找一条记录（大小写不敏感）。"""
    key = (ascii_domain or "").lower()
    for entry in data.get("domains", []):
        if str(entry.get("ascii", "")).lower() == key:
            return entry
    return None


def by_status(data: dict, *statuses) -> list:
    want = set(statuses)
    return [e for e in data.get("domains", []) if e.get("status") in want]


def add_pending(data: dict, domain: str, *, issue=None, reporter="", today=None) -> tuple:
    """登记一条 pending 投稿。

    返回 (data, entry 或 None, 拒绝原因或空串)。
    这里只做「能不能进候选池」的判断，**不代表会被展示**。
    """
    raw = normalize(domain)
    if not raw:
        return data, None, "域名是空的"

    ascii_domain = to_ascii(raw)
    if not ascii_domain or not is_valid_domain(ascii_domain):
        return data, None, f"「{domain}」不是合法域名"

    if find(data, ascii_domain):
        return data, None, f"{ascii_domain} 已经在投稿名单里了"

    reason = denied_reason(ascii_domain)
    if reason:
        return data, None, reason

    if len(data.get("domains", [])) >= COMMUNITY_CAP:
        return data, None, f"投稿总数已达上限（{COMMUNITY_CAP}），请联系维护者"

    pending = by_status(data, "pending")
    if len(pending) >= PENDING_CAP:
        return data, None, f"待审核的投稿已经排到 {PENDING_CAP} 条，请稍后再试"

    entry = {
        "domain": raw,
        "ascii": ascii_domain,
        "status": "pending",
        "source": "issue",
        "issue": issue,
        "reported_by": reporter,
        "reported_at": (today or date.today()).isoformat(),
        "approved_at": "",
        "note": "",
    }
    data.setdefault("domains", []).append(entry)
    return data, entry, ""


def target_domains(data: dict) -> list:
    """要参与抓取的投稿域名（pending 也要抓 —— 不抓就永远判不出落点）。"""
    return [(e["domain"], e["ascii"]) for e in by_status(data, "pending", "approved")]
