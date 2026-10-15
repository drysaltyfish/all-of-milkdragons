#!/usr/bin/env python3
"""
投稿的分诊（triage）—— 把一条 GitHub Issue 变成候选池里的一个 pending 域名。

**这里做的是「能不能进候选池」的判断，不是「能不能上墙」。** 上墙由
update.py 抓完之后按落点判定（见 community.classify_landing），
以及维护者手加 `approved` 标签。

子命令（都被 .github/workflows/triage-report.yml 调用）：

    extract  --body-file F            解析 Issue Form 正文，打印域名
    accept   --domain D --issue N --reporter U
                                      校验并写入 pending，打印 JSON 结果
    approve  --ascii A                维护者放行：pending -> approved
    reject   --ascii A --reason R     维护者否决
    notify                            列出还没回评过的已收录投稿（给 workflow 回评用）

为什么要单独一个脚本而不是写在 workflow 的 bash 里：这些判断（域名合法性、
是否已被模板覆盖、配额）都是纯逻辑，放这里才能被 tests/test_community.py 覆盖。
"""
import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import community as C  # noqa: E402


# ==================== Issue Form 正文解析 ====================
PLACEHOLDER = "_no response_"


def parse_form_body(body: str) -> dict:
    """把 GitHub Issue Form 渲染出来的正文解析成 {字段名: 值}。

    Issue Form 提交后正文长这样（`### ` 是表单里的 label）：

        ### 域名

        百奶宫.site

        ### 确认

        - [X] 我确认这个域名会跳转到一所真实学校的官网

    空字段会被 GitHub 填成 `_No response_`，这里归一成空串。
    """
    fields, current = {}, None
    for line in (body or "").splitlines():
        s = line.strip()
        if s.startswith("### "):
            current = s[4:].strip()
            fields.setdefault(current, "")
        elif current and s and not fields[current]:
            if s.lower() == PLACEHOLDER:
                continue
            fields[current] = s
    return fields


def extract_domain(body: str) -> str:
    """从表单正文里取域名。字段名匹配「域名」二字，容忍 label 被改过。"""
    for label, value in parse_form_body(body).items():
        if "域名" in label:
            return value
    return ""


# ==================== 是否已被模板覆盖 ====================
def template_ascii_set():
    """模板能生成的全部 punycode。用来拒绝「模板已经覆盖了」的投稿。

    ★ 懒导入：update.py 会连带加载 requests / bs4 / dns / curl_cffi，
      纯 `extract` 场景没必要付这个代价。
    """
    from update import build_targets
    from const import NAME_TREE_1, NAME_TREE_2, CN_TLDS, EN_TLDS

    seen = set()
    for tree in (NAME_TREE_1, NAME_TREE_2):
        seen |= {a for _u, a in build_targets(tree, CN_TLDS, EN_TLDS)}
    return seen


# ==================== 子命令 ====================
def out(**kw):
    print(json.dumps(kw, ensure_ascii=False))


def cmd_extract(args):
    with open(args.body_file, encoding="utf-8") as fh:
        print(extract_domain(fh.read()))
    return 0


def cmd_accept(args):
    store = C.load(args.store)
    today = date.today()

    # 1) 基本校验 + 黑名单 + 重复 + 配额，都在 add_pending 里
    store, entry, reason = C.add_pending(
        store, args.domain, issue=args.issue, reporter=args.reporter, today=today,
    )
    if entry is None:
        out(ok=False, reason=reason)
        return 0

    # 2) 模板已经覆盖的域名不用投稿（否则以后每天都会被抓，纯浪费）
    ascii_domain = entry["ascii"]
    if ascii_domain in template_ascii_set():
        out(ok=False, reason=f"{entry['domain']} 已经在自动收录范围里了，不用投稿")
        return 0

    C.save(args.store, store)
    out(ok=True, ascii=ascii_domain, domain=entry["domain"], status=entry["status"])
    return 0


def cmd_approve(args):
    """维护者放行：pending -> approved。

    ★ promote job 放行后会**自己**给 issue 回评并关闭，所以这里顺手记下
      `notified_at`。否则下一轮 refresh-data 的 notify 还会把这条已经
      回复过的投稿再回一次（同一条 issue 收到两条「已收录」）。
    """
    store = C.load(args.store)
    key = args.ascii or C.to_ascii(C.normalize(args.domain))
    if not key:
        out(ok=False, reason="没有给出可识别的域名")
        return 0
    entry = C.find(store, key)
    if entry is None:
        out(ok=False, reason="名单里没有这个域名")
        return 0
    if entry.get("status") == "approved":
        # 已经通过：可能上一轮已由 notify 回过 issue。补齐标记，
        # 避免维护者重贴 approved 标签后 promote/notify 各回一次。
        if entry.get("issue") and not entry.get("notified_at"):
            entry["notified_at"] = date.today().isoformat()
            C.save(args.store, store)
        out(ok=True, ascii=key, status="approved", note="本来就是 approved")
        return 0
    entry["status"] = "approved"
    entry["approved_at"] = date.today().isoformat()
    entry["note"] = args.note or "维护者手动放行"
    if entry.get("issue"):
        entry["notified_at"] = date.today().isoformat()
    C.save(args.store, store)
    out(ok=True, ascii=key, status="approved", note=entry["note"])
    return 0


def cmd_reject(args):
    store = C.load(args.store)
    entry = C.find(store, args.ascii)
    if entry is None:
        out(ok=False, reason="名单里没有这个域名")
        return 0
    entry["status"] = "rejected"
    entry["note"] = args.reason or "维护者手动否决"
    C.save(args.store, store)
    out(ok=True, ascii=args.ascii, status="rejected", note=entry["note"])
    return 0


def cmd_notify(args):
    """打印**还没回复过**的已收录投稿，供 workflow 回评 + 关 issue。

    输出是 tab 分隔：issue号 <TAB> 域名 <TAB> 落地域名

    ★ 幂等的唯一判据：这条投稿的 issue 还没被回复过（notified_at 为空）。
      不再用「approved_at == 今天」—— refresh-data 一天会被 workflow_dispatch
      触发多次（新投稿入池、维护者放行都会点它），按日期判断会把同一条
      已经关闭的 issue 反复回评（issue #2 就被回过两次）。
      打印前先把 notified_at 写回 store（抢占），随抓取结果一起提交；
      同一天重复触发、中途失败后重跑，都只会回评一次；
      反过来，之前漏掉的回评也不会因为过了当天而永久丢失。
    """
    store = C.load(args.store)
    changed = False
    for entry in C.by_status(store, "approved"):
        if entry.get("notified_at") or not entry.get("issue"):
            continue
        entry["notified_at"] = date.today().isoformat()
        changed = True
        print(f"{entry['issue']}\t{entry['domain']}\t{entry.get('note', '')}")
    if changed:
        C.save(args.store, store)
    return 0


def build_parser():
    p = argparse.ArgumentParser(description="网友投稿分诊")
    p.add_argument("--store", default=C.STORE_PATH)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract")
    e.add_argument("--body-file", required=True)
    e.set_defaults(func=cmd_extract)

    a = sub.add_parser("accept")
    a.add_argument("--domain", required=True)
    a.add_argument("--issue", type=int, default=None)
    a.add_argument("--reporter", default="")
    a.set_defaults(func=cmd_accept)

    ap = sub.add_parser("approve")
    ap.add_argument("--ascii", default="")
    ap.add_argument("--domain", default="")
    ap.add_argument("--note", default="")
    ap.set_defaults(func=cmd_approve)

    rj = sub.add_parser("reject")
    rj.add_argument("--ascii", required=True)
    rj.add_argument("--reason", default="")
    rj.set_defaults(func=cmd_reject)

    n = sub.add_parser("notify")
    n.set_defaults(func=cmd_notify)
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    sys.exit(args.func(args))
