#!/usr/bin/env python3
"""
校徽底板判定的回归测试（不联网）。

跑法：python3 tests/test_logo_tone.py     # 需要 Pillow

每个用例都对应线上真实踩过的坑，注释里写了域名。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from analyze_logos import analyze  # noqa: E402

FAILED = []


def check(name, cond, extra=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {extra}")
        FAILED.append(name)


TMP = tempfile.mkdtemp(prefix="tone-")
_counter = [0]


def png(rows):
    """rows: [(起始行, 结束行, (r,g,b,a))] —— 64x64，采样步长 1，比例就是真实比例。"""
    _counter[0] += 1
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    px = im.load()
    for y0, y1, color in rows:
        for y in range(y0, y1):
            for x in range(64):
                px[x, y] = color
    path = os.path.join(TMP, f"t{_counter[0]}.png")
    im.save(path)
    return path


def svg(body):
    _counter[0] += 1
    path = os.path.join(TMP, f"s{_counter[0]}.svg")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


WHITE = (255, 255, 255, 255)
NAVY = (16, 52, 121, 255)
GREY = (60, 60, 60, 255)
CLEAR = (0, 0, 0, 0)

print("\n[analyze] PNG 位图")
check("白字 + 透明底 -> light",
      analyze(png([(0, 32, WHITE)]))["tone"] == "light")
check("深蓝 logo + 透明底 -> dark",
      analyze(png([(0, 32, NAVY)]))["tone"] == "dark")
check("全透明图 -> unknown",
      analyze(png([(0, 0, CLEAR)]))["tone"] == "unknown")

# 现场：南方奶龙大学.top（南方科技大学）白墨水占比 0.68、平均亮度 0.80。
# 老判据要求「平均亮度 > 0.82 且白墨水 > 0.70」，两条都不达标，
# 白字标被判成深色 logo，摆在白底板上直接隐形。
#
# ★ 注意夹具的形状：白字标一定是「字之间/上下有透明空隙」的，
#   整张画布全不透明那是「自带实色底」（见下面 Nottingham 那个用例）。
南方 = png([(6, 27, WHITE), (33, 43, GREY)])
r = analyze(南方)
check("白字 + 投影（白墨水约 0.68、平均亮度被投影压低）-> light", r["tone"] == "light",
      f"实际 {r}")

# 现场：广东医科大学、辽宁大学…… 彩色校徽 + 白字，白墨水占比 0.55~0.61
check("彩色校徽 + 白字（白墨水约 0.56）-> light",
      analyze(png([(10, 24, WHITE), (30, 41, (10, 90, 60, 255))]))["tone"] == "light")

# ★ 例外：整张图完全不透明 = 它自带一块实色底，放深色底板上会露出一块白方块。
#   现场：宁波奶龙大学.cn（University of Nottingham）的白底 JPG，
#   白底面积太小没过 process_logos 的抠底门槛，实色底被保留了下来。
nottingham = png([(0, 64, WHITE)])
im = Image.open(nottingham).convert("RGBA")
px = im.load()
for y in range(24, 40):
    for x in range(8, 56):
        px[x, y] = NAVY
im.save(nottingham)
check("自带白底的图（整张不透明）-> dark（留在白底板上）",
      analyze(nottingham)["tone"] == "dark")

print("\n[analyze] SVG（Pillow 打不开，靠解析 fill 声明）")
# 现场：山东奶龙大学.top（山东大学）—— 整个 SVG 就是 fill: #fff，
# 以前一律返回 unknown / aspect=None，于是白 logo 摆在白底板上。
sdu = svg('<svg viewBox="0 0 524.5 162.7" xmlns="http://www.w3.org/2000/svg">'
          '<style>.cls-1 { fill: #fff; }</style>'
          '<path class="cls-1" d="M0 0h10v10H0z"/></svg>')
r = analyze(sdu)
check("CSS 里的 fill: #fff -> light", r["tone"] == "light", f"实际 {r}")
check("顺带量出 viewBox 宽高比 3.224", r["aspect"] == 3.224, f"实际 {r['aspect']}")

check("fill=\"#fff\" 属性写法 -> light",
      analyze(svg('<svg viewBox="0 0 300 100"><path fill="#fff" d="M0 0"/></svg>'))["tone"] == "light")
check("深蓝 logo -> dark",
      analyze(svg('<svg viewBox="0 0 100 100"><path fill="#163479" d="M0 0"/></svg>'))["tone"] == "dark")
check("一条 fill 都没有 -> 按 SVG 默认黑，给 dark",
      analyze(svg('<svg viewBox="0 0 100 100"><path d="M0 0"/></svg>'))["tone"] == "dark")
check("fill=\"none\" 不算颜色",
      analyze(svg('<svg viewBox="0 0 100 100"><path fill="none" stroke="#fff"/></svg>'))["tone"] == "dark")
check("深浅各半时按深处理（保守，宁可放白底板）",
      analyze(svg('<svg viewBox="0 0 100 100">'
                  '<path fill="#fff"/><path fill="#000"/></svg>'))["tone"] == "dark")

print()
if FAILED:
    print(f"❌ {len(FAILED)} 个用例失败：{FAILED}")
    sys.exit(1)
print("✅ 全部通过")
