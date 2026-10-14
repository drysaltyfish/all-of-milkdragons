#!/usr/bin/env python3
"""
网友投稿（非模板域名）的回归测试 —— 规则、配额、审核判定。

跑法：.venv/bin/python tests/test_community.py
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import community as C  # noqa: E402

FAILED = []


def check(name, cond, extra=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {extra}")
        FAILED.append(name)


# ==================== normalize ====================
print("\n[normalize] 把用户输入揉成裸域名")
check("裸域名", C.normalize("百奶宫.site") == "百奶宫.site")
check("带协议", C.normalize("https://百奶宫.site") == "百奶宫.site")
check("带路径和查询", C.normalize("https://百奶宫.site/a/b?c=1#d") == "百奶宫.site")
check("带端口", C.normalize("百奶宫.site:8080") == "百奶宫.site")
check("www 前缀", C.normalize("www.百奶宫.site") == "百奶宫.site")
check("首尾空白与末尾点", C.normalize("  百奶宫.site.  ") == "百奶宫.site")
check("全角字符", C.normalize("百奶宫．ＳＩＴＥ") == "百奶宫.site")
check("大小写归一", C.normalize("BaNaiGong.SITE") == "banaiGong.site".lower())
check("空输入", C.normalize("") == "")
check("非字符串", C.normalize(None) == "")


# ==================== to_ascii / is_valid_domain ====================
print("\n[to_ascii / is_valid_domain]")
check("中文域名转 punycode",
      C.to_ascii("百奶宫.site") == "xn--yus44ct37b.site", C.to_ascii("百奶宫.site"))
check("ASCII 域名原样", C.to_ascii("example.com") == "example.com")

check("合法域名", C.is_valid_domain("xn--yus44ct37b.site") is True)
check("单标签不算域名", C.is_valid_domain("localhost") is False)
check("IP 字面量不算域名", C.is_valid_domain("111.117.146.166") is False)
check("连续点不算", C.is_valid_domain("a..b.com") is False)
check("超长不算", C.is_valid_domain("a" * 260 + ".com") is False)
check("标签以连字符开头不算", C.is_valid_domain("-abc.com") is False)
check("下划线不算", C.is_valid_domain("a_b.com") is False)
check("纯数字 TLD 不算", C.is_valid_domain("a.123") is False)


# ==================== 黑名单 ====================
print("\n[denied_reason] 黑名单")
check("短链被拒", C.denied_reason("bit.ly") != "")
check("免费托管被拒", C.denied_reason("myproject.netlify.app") != "")
check("内容平台被拒", C.denied_reason("space.bilibili.com") != "")
check("色情关键词被拒", C.denied_reason("best-porn-site.com") != "")
check("赌博关键词被拒", C.denied_reason("casino-royal.com") != "")
check("关键词后面跟数字也拒", C.denied_reason("casino888.com") != "")
# ★ 关键：黑名单只能匹配「整段标签」或「中文子串」，
#   不能因为一个正常域名里恰好含子串就误杀
check("正常教育域名不被误杀", C.denied_reason("www.suda.edu.cn") == "")
check("bethel.edu.cn 不该被 bet 误杀",
      C.denied_reason("bethel.edu.cn") == "", C.denied_reason("bethel.edu.cn"))
check("casablanca.cn 不该被 casino 误杀", C.denied_reason("casablanca.cn") == "")
check("analytics.cn 不该被 adult 之外的词误杀", C.denied_reason("analytics.cn") == "")


# ==================== edu_landing：自动通过的唯一依据 ====================
print("\n[edu_landing] 只有受限教育域名才算数")
check(".edu.cn 算", C.edu_landing("https://www.suda.edu.cn/") is True)
check(".edu 算", C.edu_landing("https://www.mit.edu/") is True)
check(".ac.uk 算", C.edu_landing("https://www.ox.ac.uk/") is True)
check(".edu.hk 算", C.edu_landing("https://www.polyu.edu.hk/") is True)
check("裸 IP 教务系统不算（虽然它是真的大学系统）",
      C.edu_landing("http://111.117.146.166/eams/loginExt.action") is False)
check("www.gdut.cn 不算（真实大学的非教育域名）",
      C.edu_landing("https://www.gdut.cn/") is False)
check("bilibili 不算", C.edu_landing("https://space.bilibili.com/230481071") is False)
check("空 URL 不算", C.edu_landing("") is False)
# 后缀匹配必须是「域名后缀」而不是「字符串后缀」
check("伪装后缀不算", C.edu_landing("https://evil-edu.cn/") is False)
check("notedu.cn 不算", C.edu_landing("https://notedu.cn/") is False)


# ==================== classify_landing ====================
print("\n[classify_landing] 抓取结果 -> 审核决定")
TODAY = date(2026, 10, 20)
FRESH = "2026-10-19"     # 1 天前，还在宽限期内
OLD = "2026-10-01"       # 19 天前，早该出结果了

check("落到 .edu.cn -> approve",
      C.classify_landing({"final_status": 200, "final_url": "https://www.suda.edu.cn/"},
                         FRESH, TODAY) == "approve")
check("落点是拦截页 -> reject",
      C.classify_landing({"final_status": 200, "final_url": "https://dnspod.qcloud.com/x",
                          "blocked": "域名被 DNSPod 拦截"}, FRESH, TODAY) == "reject")
check("404 -> reject",
      C.classify_landing({"final_status": 404, "final_url": ""}, FRESH, TODAY) == "reject")
check("410 -> reject",
      C.classify_landing({"final_status": 410, "final_url": ""}, FRESH, TODAY) == "reject")
check("没拿到状态码 -> wait（可能是抖动）",
      C.classify_landing({"final_status": "", "final_url": ""}, FRESH, TODAY) == "wait")
check("403 -> wait（多半是限流）",
      C.classify_landing({"final_status": 403, "final_url": ""}, FRESH, TODAY) == "wait")
check("200 但落点不是教育域名 -> wait（等人工，不自动拒）",
      C.classify_landing({"final_status": 200, "final_url": "https://www.gdut.cn/"},
                         FRESH, TODAY) == "wait")
check("空行 -> reject", C.classify_landing(None, FRESH, TODAY) == "reject")

# 宽限期：投稿太久还没结果就判拒，避免 pending 无限堆积
check("403 但已过宽限期 -> reject",
      C.classify_landing({"final_status": 403, "final_url": ""}, OLD, TODAY) == "reject")
check("非教育落点但已过宽限期 -> reject",
      C.classify_landing({"final_status": 200, "final_url": "https://www.gdut.cn/"},
                         OLD, TODAY) == "reject")
check("已经 approve 的不受宽限期影响",
      C.classify_landing({"final_status": 200, "final_url": "https://a.edu.cn/"}, OLD, TODAY)
      == "approve")
check("宽限期边界：第 7 天判拒",
      C.classify_landing({"final_status": 403, "final_url": ""}, "2026-10-13", TODAY) == "reject")
check("宽限期边界：第 6 天还等",
      C.classify_landing({"final_status": 403, "final_url": ""}, "2026-10-14", TODAY) == "wait")


# ==================== add_pending ====================
print("\n[add_pending] 能不能进候选池")
store = C.empty_store()
store, entry, err = C.add_pending(store, "百奶宫.site", issue=1, reporter="alice", today=TODAY)
check("合法投稿被接受", entry is not None and not err, err)
check("状态是 pending 而不是 approved", entry["status"] == "pending")
check("记下了投稿人和日期",
      entry["reported_by"] == "alice" and entry["reported_at"] == TODAY.isoformat())
check("记下了 punycode", entry["ascii"] == "xn--yus44ct37b.site")

store, dup, err = C.add_pending(store, "https://百奶宫.site/x", issue=2, reporter="bob", today=TODAY)
check("同一个域名的不同写法判重复", dup is None and "已经在投稿名单里" in err, err)

store, bad, err = C.add_pending(store, "不是域名", issue=3, reporter="bob", today=TODAY)
check("垃圾输入被拒", bad is None and err != "", err)

store, bad, err = C.add_pending(store, "bit.ly", issue=4, reporter="bob", today=TODAY)
check("短链被拒", bad is None and "不适合" in err, err)

# 配额：pending 到顶就不再收
capped = C.empty_store()
for i in range(C.PENDING_CAP):
    capped, _e, _err = C.add_pending(capped, f"x{i}.site", issue=i, reporter="spam", today=TODAY)
capped, over, err = C.add_pending(capped, "one-more.site", issue=999, reporter="spam", today=TODAY)
check(f"pending 到 {C.PENDING_CAP} 条后不再收", over is None and "排到" in err, err)


# ==================== target_domains ====================
print("\n[target_domains] 哪些要参与抓取")
mixed = C.empty_store()
mixed["domains"] = [
    {"domain": "a.site", "ascii": "a.site", "status": "pending"},
    {"domain": "b.site", "ascii": "b.site", "status": "approved"},
    {"domain": "c.site", "ascii": "c.site", "status": "rejected"},
]
targets = dict((a, d) for d, a in C.target_domains(mixed))
check("pending 要抓（不抓就永远判不出落点）", "a.site" in targets)
check("approved 要抓", "b.site" in targets)
check("rejected 不再抓", "c.site" not in targets)


# ==================== apply_reviews（与 update.py 的集成） ====================
print("\n[apply_reviews] 抓取结果 -> 投稿状态")
import update  # noqa: E402

store = C.empty_store()
store, _e, _err = C.add_pending(store, "百奶宫.site", issue=1, reporter="alice", today=TODAY)
ascii_new = _e["ascii"]

rows = [
    # 投稿：落到真大学 -> 该自动通过
    {"ascii": ascii_new, "domain": "百奶宫.site", "final_status": 200,
     "final_url": "https://www.suda.edu.cn/"},
    # 模板域名：不该被动到
    {"ascii": "xn--template.top", "domain": "模板.top", "final_status": 200,
     "final_url": "https://x.edu.cn/"},
]
kept, store, changes = update.apply_reviews(rows, store, TODAY)
by = {r["ascii"]: r for r in kept}
check("落点在教育域名 -> 自动 approved",
      C.find(store, ascii_new)["status"] == "approved", C.find(store, ascii_new))
check("打上了 community 标记", by[ascii_new].get("source") == "community")
check("模板域名不受影响（无 source 标记）", by["xn--template.top"].get("source", "") == "")
check("模板域名仍然保留", "xn--template.top" in by)
check("变化被记录", any(c[0] == ascii_new and c[1] == "approved" for c in changes))

# 落到拦截页 -> rejected，且该行被丢掉（于是校徽会被 prune 掉）
store2 = C.empty_store()
store2, e2, _ = C.add_pending(store2, "坏域名.site", issue=2, reporter="mallory", today=TODAY)
rows2 = [{"ascii": e2["ascii"], "domain": "坏域名.site", "final_status": 200,
          "final_url": "https://dnspod.qcloud.com/x", "blocked": "域名被 DNSPod 拦截"}]
kept2, store2, changes2 = update.apply_reviews(rows2, store2, TODAY)
check("落到拦截页 -> rejected", C.find(store2, e2["ascii"])["status"] == "rejected")
check("rejected 的行不留在 result.json（校徽随之被清理）", kept2 == [])

# 还在 pending：既不上墙，也不否掉
store3 = C.empty_store()
store3, e3, _ = C.add_pending(store3, "慢域名.site", issue=3, reporter="bob", today=TODAY)
rows3 = [{"ascii": e3["ascii"], "domain": "慢域名.site", "final_status": 403, "final_url": ""}]
kept3, store3, _ = update.apply_reviews(rows3, store3, TODAY)
check("403 -> 保持 pending 且不上墙",
      C.find(store3, e3["ascii"])["status"] == "pending" and kept3 == [])

# 已通过的老投稿即使这轮挂了也要留着（交给 3 天宽限期）
store4 = C.empty_store()
store4["domains"] = [{"domain": "老投稿.site", "ascii": "xn--old.site", "status": "approved",
                      "reported_at": "2026-01-01"}]
rows4 = [{"ascii": "xn--old.site", "domain": "老投稿.site", "final_status": 503, "final_url": ""}]
kept4, store4, _ = update.apply_reviews(rows4, store4, TODAY)
check("已通过的投稿暂时挂了也留着（失联宽限期接手）",
      len(kept4) == 1 and kept4[0]["source"] == "community")


# ==================== 存储往返 ====================
print("\n[load/save] 读写往返")
import tempfile  # noqa: E402

tmp = os.path.join(tempfile.mkdtemp(prefix="community-"), "store.json")
C.save(tmp, store)
back = C.load(tmp)
check("保存后能读回来", len(back["domains"]) == len(store["domains"]))
check("不存在的文件返回空 store", C.load("/nonexistent/nope.json")["domains"] == [])
check("坏文件返回空 store",
      (open(tmp + ".bad", "w").write("{not json"), C.load(tmp + ".bad")["domains"] == [])[1])


# ==================== Issue Form 正文解析 ====================
# 这段解析的是 GitHub 把 Issue Form 渲染出来的正文格式，
# 一旦 GitHub 改了渲染方式，这里会先炸 —— 所以值得锁住。
print("\n[extract_domain] 从 Issue Form 正文里取域名")
import triage_report as T  # noqa: E402

SAMPLE = """### 域名

百奶宫.site

### 说明（可选）

跳转到苏州大学

### 确认

- [X] 我确认这个域名会跳转到一所真实学校的官网
"""

body = T.parse_form_body(SAMPLE)
check("按 ### 切成字段", "域名" in body and "说明（可选）" in body)
check("取到域名", T.extract_domain(SAMPLE) == "百奶宫.site", T.extract_domain(SAMPLE))
check("只取第一行（不把后面的说明吞进来）",
      "\n" not in T.extract_domain(SAMPLE))

# GitHub 对空字段会填 _No response_
EMPTY_NOTE = """### 域名

abc.site

### 说明（可选）

_No response_

### 确认

- [X] 我确认
"""
check("空字段占位符被忽略", T.extract_domain(EMPTY_NOTE) == "abc.site")

# 只有确认框勾了、域名空着
NO_DOMAIN = """### 域名

_No response_

### 确认

- [X] 我确认
"""
check("域名空 -> 空串", T.extract_domain(NO_DOMAIN) == "")
check("完全不是表单 -> 空串", T.extract_domain("随便写的一句话") == "")
check("空正文 -> 空串", T.extract_domain("") == "")

# 带协议、带路径、带空格的输入也要能救回来
MESSY = "### 域名\n\nhttps://百奶宫.site/abc\n\n### 确认\n\n- [X] 我确认\n"
check("表单里填了完整 URL 也能解析出来",
      C.normalize(T.extract_domain(MESSY)) == "百奶宫.site")

# workflow 里是用 `approve --domain` 调的（表单里可能填的是完整 URL），
# 所以这里锁住「approve 自己会做归一化」这件事。
import argparse as _ap  # noqa: E402

print("\n[approve --domain] 手动放行也要自己归一化")
tmp2 = os.path.join(tempfile.mkdtemp(prefix="approve-"), "s.json")
st2 = C.empty_store()
st2, _e2, _ = C.add_pending(st2, "百奶宫.site", issue=5, reporter="a", today=TODAY)
C.save(tmp2, st2)
T.cmd_approve(_ap.Namespace(store=tmp2, ascii="", domain="https://百奶宫.site/abc", note="x"))
check("完整 URL 也能放行",
      C.find(C.load(tmp2), "xn--yus44ct37b.site")["status"] == "approved")
T.cmd_approve(_ap.Namespace(store=tmp2, ascii="", domain="没这个域名.com", note="x"))
check("未知域名不会被悄悄加进去",
      C.find(C.load(tmp2), C.to_ascii("没这个域名.com")) is None)


print()
if FAILED:
    print(f"❌ {len(FAILED)} 个用例失败：{FAILED}")
    sys.exit(1)
print("✅ 全部通过")
