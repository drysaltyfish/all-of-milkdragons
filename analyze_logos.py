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

  · tone=light   不透明像素里过半接近纯白 -> 前端给它深色底板
  · tone=dark    其余 -> 常规白色底板
  · tone=unknown 解码失败 -> 当作 dark 处理
  · aspect       宽高比，>1 是横排字标，前端可据此决定缩放策略

判定依据只有一条：**白墨水占全部墨水的比例**。
不掺「整张图平均亮度」—— 白字标常常带投影、描边、抗锯齿边缘，平均亮度会被
压到 0.8 以下，两个条件一起要求就会漏掉一大批白 logo（下面阈值那段有详细记录）。

用法：python3 analyze_logos.py
"""
import json
import os
import re
import sys
from statistics import median

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("需要 Pillow：python3 -m pip install pillow")

RESULT_JSON = "result.json"
OUT_JSON = "logo_tones.json"

# 判定阈值：不透明像素里有多大比例接近纯白。
#
# ★ 只看「白墨水占比」，不再要求「平均亮度也够高」。
#   以前写的是 `mean > 0.82 AND whitish > 0.70`，两条都得满足 —— 太严了。
#   线上有 17 张白色字标（南方科技大学、辽宁大学、哈尔滨理工大学、广州大学、
#   复旦大学、广东医科大学……）白墨水占比落在 0.51~0.71，平均亮度又被阴影和
#   抗锯齿边缘压到 0.73~0.85，于是两条都不达标、被判成深色 logo，
#   摆在白色底板上白字直接隐形。
#   改成只看白墨水占比 >= 0.5 之后，这 17 张全部归位；同时因为「过半墨水
#   是白的」本来就意味着白底板没法看，这个阈值也不会把深色 logo 误伤进深色底板。
WHITISH_RATIO_LIGHT = 0.5
# 单个像素亮到这个程度才算「白墨水」
WHITISH_LUMA = 0.85

# 整张图完全不透明 = 它自带一整块实色底（白底 / 深蓝底……），
# 不是「白 logo + 透明底」。这种图放深色底板上会露出一块白/蓝色方块，
# 所以永远给白底板。
# （实测只有宁波奶龙大学.cn 这张 Nottingham 的白底 JPG：它底下白底面积太小，
#   没过 process_logos 的 MIN_REMOVED_RATIO，所以实色底被保留了下来。）
OPAQUE_RATIO_BAKED = 0.98

SAMPLE_BUDGET = 64  # 每个方向最多采 64 个点，几十毫秒一张


def luma(r, g, b):
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def opaque_ratio(img):
    """alpha > 16 的像素占比。"""
    total = img.width * img.height
    if not total:
        return 0.0
    return sum(img.getchannel("A").histogram()[17:]) / total


def analyze_raster(path):
    try:
        im = Image.open(path).convert("RGBA")
    except Exception:
        return {"tone": "unknown", "aspect": None}

    aspect = round(im.width / im.height, 3) if im.height else None
    step_x = max(1, im.width // SAMPLE_BUDGET)
    step_y = max(1, im.height // SAMPLE_BUDGET)

    total = 0
    whitish = 0
    for y in range(0, im.height, step_y):
        for x in range(0, im.width, step_x):
            r, g, b, a = im.getpixel((x, y))
            if a < 40:  # 透明像素不算
                continue
            total += 1
            if luma(r, g, b) > WHITISH_LUMA:
                whitish += 1

    if total == 0:  # 整张图都是透明的
        return {"tone": "unknown", "aspect": aspect}

    # 自带实色底的图：给白底板，深色底板上会露出一整块色块
    if opaque_ratio(im) >= OPAQUE_RATIO_BAKED:
        return {"tone": "dark", "aspect": aspect}

    ratio = whitish / total
    tone = "light" if ratio >= WHITISH_RATIO_LIGHT else "dark"
    return {"tone": tone, "aspect": aspect}


# ==================== SVG ====================
# Pillow 打不开 SVG，所以退一步读它声明的填充色。
# 这批白 logo 的 SVG 恰好都是 `fill: #fff` / `fill="#fff"` 这种直给写法，
# 数一数浅色 / 深色声明各有多少条就能判出来 —— 够用，且不用引入 cairosvg。
_FILL_RE = re.compile(r'fill\s*[:=]\s*["\']?\s*([^"\';>}]+)', re.I)
_VIEWBOX_RE = re.compile(
    r'viewBox\s*=\s*["\']\s*([-\d.]+)[,\s]+([-\d.]+)[,\s]+([-\d.]+)[,\s]+([-\d.]+)',
    re.I,
)
_NAMED_LIGHT = {"white", "snow", "ivory", "ghostwhite"}
_NAMED_DARK = {"black"}
_SKIP = {"none", "transparent", "currentcolor", "inherit", "initial", "unset"}


def parse_color(token):
    """把 SVG 里的颜色写法归一成 (r, g, b)；认不出来返回 None。"""
    t = token.strip().lower().rstrip(";").strip()
    if not t or t in _SKIP or t.startswith("url("):
        return None
    if t in _NAMED_LIGHT:
        return (255, 255, 255)
    if t in _NAMED_DARK:
        return (0, 0, 0)
    if t.startswith("#"):
        h = t[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) in (6, 8):
            try:
                return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                return None
        return None
    m = re.match(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)", t)
    if m:
        return tuple(min(255, int(float(x))) for x in m.groups())
    return None


def svg_aspect(text):
    m = _VIEWBOX_RE.search(text)
    if not m:
        return None
    try:
        w, h = float(m.group(3)), float(m.group(4))
    except ValueError:
        return None
    return round(w / h, 3) if h > 0 else None


def analyze_svg(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return {"tone": "unknown", "aspect": None}

    aspect = svg_aspect(text)
    colors = [c for c in (parse_color(raw) for raw in _FILL_RE.findall(text)) if c]

    # 一条 fill 都没声明 -> 按 SVG 默认（黑）算，给白底板
    if not colors:
        return {"tone": "dark", "aspect": aspect}

    light = sum(1 for c in colors if luma(*c) > WHITISH_LUMA)
    tone = "light" if light * 2 > len(colors) else "dark"
    return {"tone": tone, "aspect": aspect}


def analyze(path):
    if path.lower().endswith(".svg"):
        return analyze_svg(path)
    return analyze_raster(path)


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
    unknown = [p for p, v in tones.items() if v["tone"] == "unknown"]
    aspects = [v["aspect"] for v in tones.values() if v["aspect"]]
    print(
        f"\n共 {len(tones)} 张：浅色 {len(light)} 张，深色 {len(tones) - len(light) - len(unknown)} 张，"
        f"未知 {len(unknown)} 张；宽高比中位数 "
        f"{median(aspects):.2f} -> {OUT_JSON}"
    )


if __name__ == "__main__":
    main()
