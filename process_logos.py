#!/usr/bin/env python3
"""
校徽后处理 —— 去底色 + 修尺寸。

解决两个实际问题：
  1. **很多校徽带一块实色底**（抓的是站点导航栏/横幅里的方形图，常常是白底、
     深蓝底、紫底……），放在卡片托盘上就是一块突兀的色块。这里沿边缘做容差
     洪水填充，把与边缘同色的部分抠成透明（只抠与边缘连通的区域，
     所以 logo 内部的同色细节不会被误伤）。
  2. **尺寸很离谱**：抓到过 8072×1670 的 PNG，也有一堆四周留白极大的图。
     这里按 alpha 边界裁掉空白，并把最长边压到 MAX_EDGE。

原地覆盖 `logos/`：update.py 每次都会重新下载覆盖，所以这个脚本是幂等的。

用法：python3 process_logos.py
"""
import io
import json
import os
import sys

try:
    from PIL import Image, ImageChops, ImageDraw
except ImportError:  # pragma: no cover
    sys.exit("需要 Pillow：python3 -m pip install pillow")

RESULT_JSON = "result.json"

# 最长边上限。卡片里校徽最大显示宽度约 250 CSS px，640 足够 2 倍屏。
MAX_EDGE = 640
# flood fill 的颜色容差（RGBA 四通道差之和），越大抠得越狠
BG_TOLERANCE = 34
# 边缘采样点里有多少比例必须接近背景色，才认为「这张图有实色底」
BG_UNIFORM_RATIO = 0.85
# 边缘不透明点少于这个比例，说明本来就是透明底，没有底可抠
BG_MIN_SOLID_BORDER = 0.6
# 抠掉的面积至少占全图这个比例，才算「真的有一块底」而不是零散同色像素
MIN_REMOVED_RATIO = 0.18
# 采到的背景色之间允许的散布
BG_SPREAD = 40
# 抠完之后不透明像素少于这个比例，就认为抠过头了，保留原图
MIN_KEEP_RATIO = 0.02
# Pillow 处理超大图会炸（解压炸弹保护），需要放开
Image.MAX_IMAGE_PIXELS = None

SVG_SUFFIX = (".svg",)


def border_points(w, h, count_per_edge=9):
    """沿四条边均匀取点，用来估计底色 + 作为洪水填充的种子。"""
    xs = [round(i * (w - 1) / (count_per_edge - 1)) for i in range(count_per_edge)]
    ys = [round(i * (h - 1) / (count_per_edge - 1)) for i in range(count_per_edge)]
    pts = []
    for x in xs:
        pts.append((x, 0))
        pts.append((x, h - 1))
    for y in ys:
        pts.append((0, y))
        pts.append((w - 1, y))
    # 去重但保序
    return list(dict.fromkeys(pts))


def color_close(a, b, tol):
    return sum(abs(x - y) for x, y in zip(a, b)) <= tol


def opaque_ratio(img):
    alpha = img.getchannel("A")
    hist = alpha.histogram()
    total = img.width * img.height
    if total == 0:
        return 0.0
    # 认为 alpha > 16 的算不透明
    opaque = sum(hist[17:])
    return opaque / total


def border_transparent_ratio(img):
    """边缘有多少比例是全透明的。"""
    px = img.load()
    pts = border_points(img.width, img.height)
    if not pts:
        return 0.0
    return sum(1 for p in pts if px[p][3] < 16) / len(pts)


def detect_background(img):
    """判断这张图有没有「一块统一的实色底」。

    ★ 关键：只看**不透明**的边缘点。
      白字透明底的 logo，边缘上不透明的点只有笔画扫过的那几个，
      如果把它也算成「底色是白」，洪水填充会把整个字都吃掉。

    返回 (背景色, 参与判断的边缘点)；没有统一底色则返回 (None, [])。
    """
    px = img.load()
    points = border_points(img.width, img.height)
    solid = [p for p in points if px[p][3] >= 16]

    # 边缘大部分是透明的 -> 本来就是透明底，没有底色可抠
    if len(solid) < len(points) * BG_MIN_SOLID_BORDER:
        return None, []

    samples = [px[p][:3] for p in solid]
    ref = samples[0]
    close = [s for s in samples if color_close(s, ref, BG_SPREAD)]
    if len(close) / len(samples) < BG_UNIFORM_RATIO:
        return None, []

    n = len(close)
    bg = (sum(s[0] for s in close) // n,
          sum(s[1] for s in close) // n,
          sum(s[2] for s in close) // n)
    seeds = [p for p in solid if color_close(px[p][:3], ref, BG_SPREAD)]
    return bg, seeds


def pick_sentinel(img):
    """找一个图里不存在的填充色，避免和 logo 自身颜色撞车。"""
    try:
        colors = img.convert("RGB").getcolors(maxcolors=1 << 22)
    except Exception:
        colors = None
    palette = {c for _, c in colors} if colors else set()
    for candidate in ((255, 0, 255), (0, 255, 0), (255, 255, 0), (0, 255, 255)):
        if candidate not in palette:
            return candidate
    return (255, 0, 255)


def trim(img):
    """按 alpha 边界裁掉四周空白。"""
    bbox = img.getchannel("A").getbbox()
    return img.crop(bbox) if bbox else img


def limit_size(img):
    """把最长边压到 MAX_EDGE 以内（不放大）。"""
    longest = max(img.width, img.height)
    if longest > MAX_EDGE:
        scale = MAX_EDGE / longest
        size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        img = img.resize(size, Image.LANCZOS)
    return img


def remove_background(img):
    """沿边缘洪水填充抠底。返回 (新图, 是否真的抠了)。

    ★ 必须在 trim() 之后调用。很多抓到的校徽是「透明外边距 + 中间一块实色矩形」，
      直接看原图边缘会以为它已经是透明底而跳过，结果卡片上留一块白/蓝/紫的方框。
    """
    _bg, seeds = detect_background(img)
    if not seeds:
        return img, False

    rgb = img.convert("RGB")
    sentinel = pick_sentinel(img)
    px = rgb.load()
    for x, y in seeds:
        if px[x, y] == sentinel:
            continue
        # ImageDraw.floodfill 是模块级函数，不是 Draw 的方法
        ImageDraw.floodfill(rgb, (x, y), sentinel, thresh=BG_TOLERANCE)

    # 生成「保留」蒙版：不等于填充色的地方为 255
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, sentinel)).convert("L")
    keep = diff.point(lambda v: 0 if v == 0 else 255)

    out = img.copy()
    out.putalpha(ImageChops.multiply(img.getchannel("A"), keep))

    total = img.width * img.height
    removed = total - sum(keep.histogram()[128:])
    # 抠掉的面积太小 -> 那只是零散的同色像素，不是一块底
    if removed < total * MIN_REMOVED_RATIO:
        return img, False
    # 抠完什么都不剩 -> 说明抠过头了（把 logo 本身吃掉了）
    if opaque_ratio(out) < MIN_KEEP_RATIO:
        return img, False
    return out, True


def main():
    if not os.path.exists(RESULT_JSON):
        sys.exit(f"找不到 {RESULT_JSON}")

    with open(RESULT_JSON, encoding="utf-8") as fh:
        rows = json.load(fh)

    paths = sorted({row["logo_path"] for row in rows if row.get("logo_path")})

    stats = {"total": 0, "cut": 0, "changed": 0, "skipped": 0, "failed": 0,
             "bytes_before": 0, "bytes_after": 0}

    for path in paths:
        if not os.path.isfile(path):
            continue
        if path.lower().endswith(SVG_SUFFIX):
            stats["skipped"] += 1
            continue

        stats["total"] += 1
        before_bytes = os.path.getsize(path)

        try:
            with Image.open(path) as handle:
                original = handle.convert("RGBA")
        except Exception as exc:
            print(f"  跳过（打不开）：{path} {exc}")
            stats["failed"] += 1
            stats["bytes_before"] += before_bytes
            stats["bytes_after"] += before_bytes
            continue

        original_size = original.size
        already_transparent = border_transparent_ratio(original) > 0.5

        # 先裁掉透明外边距，再判断/抠底色，最后再裁一次 + 限尺寸
        img = trim(original)
        img, cut = remove_background(img)
        img = limit_size(trim(img))

        # 抠完只剩一条线之类的病态结果，退回只做尺寸归一
        if img.width < 8 or img.height < 8:
            img = limit_size(trim(original))
            cut = False

        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        data = buffer.getvalue()

        # 缩放/优化后反而变大时保留原文件（去底色和超尺寸图除外，
        # 那两种情况必须落盘）
        oversized = max(original_size) > MAX_EDGE
        if cut or oversized or len(data) <= before_bytes:
            with open(path, "wb") as fh:
                fh.write(data)
            after_bytes = len(data)
        else:
            after_bytes = before_bytes

        stats["cut"] += int(cut)
        stats["bytes_before"] += before_bytes
        stats["bytes_after"] += after_bytes

        resized = img.size != original_size
        if resized:
            stats["changed"] += 1

        if cut or resized or not already_transparent:
            marks = " + ".join(
                m for m, on in (("去底色", cut), ("裁剪/缩放", resized)) if on
            )
            print(
                f"  {path}: {original_size[0]}x{original_size[1]} -> {img.width}x{img.height}"
                f"  {before_bytes / 1024:.0f}KB -> {after_bytes / 1024:.0f}KB  {marks}"
            )

    saved = stats["bytes_before"] - stats["bytes_after"]
    print(
        f"\n处理 {stats['total']} 张：去底色 {stats['cut']} 张，尺寸变化 {stats['changed']} 张，"
        f"跳过 {stats['skipped']} 张（SVG），失败 {stats['failed']} 张。\n"
        f"体积 {stats['bytes_before'] / 1048576:.2f} MB -> {stats['bytes_after'] / 1048576:.2f} MB"
        f"（省 {saved / 1048576:.2f} MB）"
    )


if __name__ == "__main__":
    main()
