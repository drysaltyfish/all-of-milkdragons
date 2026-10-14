#!/usr/bin/env python3
"""
清理 logos/ 里已经不被 result.json 引用的图。

为什么需要：update.py 只写不删，某个域名这次没抓到校徽、下次又抓到了，
旧文件就会一直躺在仓库里。日报级别刷新下，这些垃圾会稳定增长。

用法：python3 prune_logos.py
"""
import json
import os
import sys

RESULT_JSON = "result.json"
LOGO_DIR = "logos"


def main():
    if not os.path.exists(RESULT_JSON):
        sys.exit(f"找不到 {RESULT_JSON}")

    with open(RESULT_JSON, encoding="utf-8") as fh:
        rows = json.load(fh)

    referenced = {
        os.path.normpath(row["logo_path"])
        for row in rows
        if row.get("logo_path")
    }

    if not os.path.isdir(LOGO_DIR):
        print(f"{LOGO_DIR}/ 不存在，没什么可清理的。")
        return

    removed, freed = 0, 0
    for name in sorted(os.listdir(LOGO_DIR)):
        path = os.path.join(LOGO_DIR, name)
        if not os.path.isfile(path):
            continue
        if os.path.normpath(path) in referenced:
            continue
        freed += os.path.getsize(path)
        os.remove(path)
        removed += 1
        print(f"  删除 {path}")

    print(f"清理完成：删除 {removed} 个未被引用的文件，释放 {freed / 1024:.1f} KB。")


if __name__ == "__main__":
    main()
