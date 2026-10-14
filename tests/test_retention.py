#!/usr/bin/env python3
"""
指数退避 / 历史保留 / 校徽按落地域名去重 的回归测试（纯函数，不联网）。

跑法：.venv/bin/python tests/test_retention.py
"""
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import update  # noqa: E402
from update import (  # noqa: E402
    backoff_delay,
    classify_error,
    is_up,
    logo_key,
    merge_history,
    parse_date,
    resolve_logo,
)

FAILED = []


def check(name, cond, extra=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {extra}")
        FAILED.append(name)


# ==================== 指数退避 ====================
print("\n[backoff_delay] 三级退避，封顶 30s")
check("第 1 级 = 5s", backoff_delay(0) == 5.0, backoff_delay(0))
check("第 2 级 = 15s", backoff_delay(1) == 15.0, backoff_delay(1))
check("第 3 级 = 30s（45 被上限截断）", backoff_delay(2) == 30.0, backoff_delay(2))
check("再往后不会超过上限", backoff_delay(9) == update.BACKOFF_MAX, backoff_delay(9))
check("正好三级", update.BACKOFF_TIERS == 3, update.BACKOFF_TIERS)
check("上限就是 30s", update.BACKOFF_MAX == 30.0, update.BACKOFF_MAX)

print("\n[classify_error] requests / curl_cffi 的异常都要认")
try:
    raise TimeoutError("read timed out")
except Exception as e:
    check("超时 -> timeout", classify_error(e) == "timeout")


class ConnectTimeout(Exception):
    pass


class TooManyRedirects(Exception):
    pass


class RequestsError(Exception):
    pass


check("ConnectTimeout -> timeout", classify_error(ConnectTimeout("x")) == "timeout")
check("TooManyRedirects -> too_many_redirects",
      classify_error(TooManyRedirects("x")) == "too_many_redirects")
check("curl_cffi 的 RequestsError 归到 conn_error",
      classify_error(RequestsError("Failed to connect")) == "conn_error")


# ==================== is_up ====================
print("\n[is_up] 口径必须和前端 statusBadgeOf() 一致")
check("200 -> 通", is_up({"final_status": 200}) is True)
check("301 -> 通", is_up({"final_status": 301}) is True)
check("403 -> 不通", is_up({"final_status": 403}) is False)
check("没拿到状态码 -> 不通", is_up({"final_status": ""}) is False)
# 落点是中间页/拦截页的，即使 HTTP 200 也不能算通
check("blocked 即使 200 也不算通",
      is_up({"final_status": 200, "blocked": "域名被停放，跳到了百度"}) is False)


# ==================== parse_date ====================
print("\n[parse_date]")
check("YYYY-MM-DD", parse_date("2026-10-14") == date(2026, 10, 14))
check("带时间的 ISO 串", parse_date("2026-10-14T03:00:00Z") == date(2026, 10, 14))
check("空 -> None", parse_date("") is None)
check("垃圾 -> None", parse_date("不是日期") is None)
check("None -> None", parse_date(None) is None)


# ==================== merge_history ====================
print("\n[merge_history] 失联不立刻删，满 3 天才移除")
TODAY = date(2026, 10, 14)

# a：10-10 就失联了（4 天）-> 该移除
# b：历史上有、这轮 403 -> 今天开始算失联，保留且内容沿用
# c：这轮通了 -> 收录
# d：从没记录过、这轮也没通 -> 不收录（否则 5 万候选会全写进 result.json）
# e：历史上还在宽限期内、这轮连候选都没有 -> 继续挂着
prev = [
    {"ascii": "a", "domain": "a.top", "down_since": "2026-10-10",
     "title": "旧 A", "final_status": 200, "logo_path": "logos/a.png"},
    {"ascii": "b", "domain": "b.top", "title": "B 大学",
     "final_status": 200, "logo_path": "logos/b.png", "logo_url": "http://b.edu.cn/l.png"},
    {"ascii": "c", "domain": "c.top", "title": "C 大学", "final_status": 200},
    {"ascii": "e", "domain": "e.top", "title": "E 大学", "down_since": "2026-10-13",
     "final_status": 200},
]
rows = [
    {"ascii": "a", "domain": "a.top", "final_status": ""},
    {"ascii": "b", "domain": "b.top", "final_status": 403, "title": "", "logo_path": ""},
    {"ascii": "c", "domain": "c.top", "final_status": 200, "title": "C 大学"},
    {"ascii": "d", "domain": "d.top", "final_status": ""},
]
kept, retired = merge_history(rows, prev, TODAY)
by = {r["ascii"]: r for r in kept}

check("连续失联满 3 天 -> 移除", "a" not in by and retired == ["a.top"], f"{retired}")
check("刚失联 -> 保留，并记下失联日期", by.get("b", {}).get("down_since") == "2026-10-14",
      by.get("b"))
check("刚失联 -> 标题沿用历史，卡片不空白", by.get("b", {}).get("title") == "B 大学")
check("刚失联 -> 校徽也沿用历史",
      by.get("b", {}).get("logo_path") == "logos/b.png")
check("通了 -> 清空 down_since 并刷新 last_ok",
      by.get("c", {}).get("down_since") == "" and by.get("c", {}).get("last_ok") == "2026-10-14")
check("从没记录过又没通 -> 不收录", "d" not in by)
check("历史里还在宽限期内 -> 继续挂着", by.get("e", {}).get("down_since") == "2026-10-13",
      by.get("e"))

# 宽限期边界：恰好满 3 天移除，2 天保留
kept2, ret2 = merge_history(
    [{"ascii": "x", "domain": "x.top", "final_status": ""}],
    [{"ascii": "x", "domain": "x.top", "down_since": "2026-10-12"}],
    TODAY,
)
check("失联 2 天 -> 保留", len(kept2) == 1 and not ret2, f"{kept2} {ret2}")

# 第一次运行：没有任何历史，且全都失败 -> result.json 不应被写进 5 万行
kept3, ret3 = merge_history(
    [{"ascii": f"n{i}", "domain": f"n{i}.top", "final_status": ""} for i in range(200)],
    [],
    TODAY,
)
check("首次运行、全部失联 -> 一行都不写入",
      kept3 == [] and ret3 == [], f"kept={len(kept3)} retired={len(ret3)}")


# ==================== logo_key ====================
print("\n[logo_key] 按「重定向后的域名」当 key")
check("同一个学校的不同路径 -> 同一个 key",
      logo_key("https://www.scut.edu.cn/") == logo_key("https://www.scut.edu.cn/new/"))
check("同一个学校的不同奶龙域名 -> 同一个 key",
      logo_key("https://www.lnu.edu.cn/") == logo_key("https://www.lnu.edu.cn/index.html"))
check("不同学校 -> 不同 key",
      logo_key("https://www.lnu.edu.cn/") != logo_key("https://www.pku.edu.cn/"))
check("非 ASCII 域名转 punycode",
      logo_key("https://中文.中国/") == "xn--fiq228c.xn--fiqs8s", logo_key("https://中文.中国/"))
check("空 URL -> 空 key", logo_key("") == "")
check("超长域名被截断且仍唯一",
      logo_key("https://" + "a" * 120 + ".com/") != logo_key("https://" + "a" * 121 + ".com/")
      and len(logo_key("https://" + "a" * 120 + ".com/")) <= 80)


# ==================== resolve_logo 去重 ====================
print("\n[resolve_logo] 同一个落地域名只下一次、只存一份")
TMP = tempfile.mkdtemp(prefix="logo-dedupe-")
_orig_logo_dir = update.LOGO_DIR
update.LOGO_DIR = TMP
calls = []


def fake_download(session, url, out_dir, name, referer=None):
    calls.append(name)
    path = os.path.join(out_dir, f"{name}.png")
    with open(path, "wb") as fh:
        fh.write(b"x" * 128)
    return path


_orig_download = update.download_logo
update.download_logo = fake_download
try:
    update._LOGO_BY_KEY.clear()
    p1 = resolve_logo(None, "https://www.lnu.edu.cn/logo.png", "www.lnu.edu.cn")
    p2 = resolve_logo(None, "https://www.lnu.edu.cn/logo.png", "www.lnu.edu.cn")
    check("同一落地域名只下载一次", len(calls) == 1, calls)
    check("两次拿到同一个路径", p1 == p2 and p1.endswith("www.lnu.edu.cn.png"), (p1, p2))

    p3 = resolve_logo(None, "https://www.pku.edu.cn/l.png", "www.pku.edu.cn")
    check("换个学校才会再下一次", len(calls) == 2 and p3 != p1, calls)

    check("空 key 直接返回空", resolve_logo(None, "https://x/l.png", "") == "")
    check("空 URL 直接返回空", resolve_logo(None, "", "www.lnu.edu.cn") == "")
    check("文件名就是落地域名，不是奶龙域名",
          os.path.basename(p1) == "www.lnu.edu.cn.png", os.path.basename(p1))
finally:
    update.download_logo = _orig_download
    update.LOGO_DIR = _orig_logo_dir


print()
if FAILED:
    print(f"❌ {len(FAILED)} 个用例失败：{FAILED}")
    sys.exit(1)
print("✅ 全部通过")
