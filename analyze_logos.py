#!/usr/bin/env python3
"""
校徽体检 —— 生成 `logo_tones.json`，供前端决定校徽摆在哪块底板上。

为什么需要它：抓下来的校徽里，很大一部分是「白色 logo + 透明背景」
（站点导航栏用的白色版本），直接放在白色卡片上等于隐形。Node 侧的
`scripts/build-data.mjs` 没有图片解码能力，所以这里用 Python 把结论一次性
算好、写进版本库，构建流水线只读结果、不依赖 Pillow。

产出（logo_tones.json）：
    {
      "logos/xxx.png": { "tone": "light" | "dark" | "unknown", "aspect": 3.21 }
    }

  · tone=light   绝大多数不透明像素接近纯白 -> 前端给它深色底板
  · tone=dark    其余 -> 常规白色底板
  · tone=unknown SVG / 解码失败 -> 当作 dark 处理
  · aspect       宽高比，>1 是横排字标，前端可据此决定缩放策略

用法：python3 analyze_logos.py
"""
import json
import os
import sys
from statistics import median

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("需要 Pillow：python3 -m pip install pillow")

RESULT_JSON = "result.json"
OUT_JSON = "logo_tones.json"

# 判定阈值：平均亮度够高、且绝大多数不透明像素都接近纯白
MEAN_LUMA_LIGHT = 0.82
WHITISH_RATIO_LIGHT = 0.70

SAMPLE_BUDGET = 64  # 每个方向最多采 64 个点，几十毫秒一张


def luma(r, g, b):
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def analyze(path):
    try:
        im = Image.open(path).convert("RGBA")
    except Exception:
        return {"tone": "unknown", "aspect": None}

    aspect = round(im.width / im.height, 3) if im.height else None
    step_x = max(1, im.width // SAMPLE_BUDGET)
    step_y = max(1, im.height // SAMPLE_BUDGET)

    total = 0
    luma_sum = 0.0
    whitish = 0
    for y in range(0, im.height, step_y):
        for x in range(0, im.width, step_x):
            r, g, b, a = im.getpixel((x, y))
            if a < 40:  # 透明像素不算
                continue
            total += 1
            value = luma(r, g, b)
            luma_sum += value
            if value > 0.85:
                whitish += 1

    if total == 0:  # 整张图都是透明的
        return {"tone": "unknown", "aspect": aspect}

    mean = luma_sum / total
    ratio = whitish / total
    tone = "light" if (mean > MEAN_LUMA_LIGHT and ratio > WHITISH_RATIO_LIGHT) else "dark"
    return {"tone": tone, "aspect": aspect}


def main():
    if not os.path.exists(RESULT_JSON):
        sys.exit(f"找不到 {RESULT_JSON}")

    with open(RESULT_JSON, encoding="utf-8") as fh:
        rows = json.load(fh)

    paths = sorted({row["logo_path"] for row in rows if row.get("logo_path")})
    tones = {}
    for path in paths:
        if not os.path.exists(path):
            print(f"  跳过（文件不存在）：{path}")
            continue
        tones[path] = analyze(path)
        print(f"  {tones[path]['tone']:<7} aspect={str(tones[path]['aspect']):<8} {path}")

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(tones, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    light = [p for p, v in tones.items() if v["tone"] == "light"]
    aspects = [v["aspect"] for v in tones.values() if v["aspect"]]
    print(
        f"\n共 {len(tones)} 张：浅色 {len(light)} 张，深色 {len(tones) - len(light)} 张；"
        f"宽高比中位数 {median(aspects):.2f} -> {OUT_JSON}"
    )


if __name__ == "__main__":
    main()
