#!/usr/bin/env python3
"""
阶段 3 页面解析（parse_page / degraded_reason / save_inline_svg）的回归测试。

跑法：python tests/test_page_assets.py

每一个用例都对应一个**真实踩过的现场**：
  · 北医（bjmu）的校徽是 <a class="web-logo"><svg …/></a> —— 旧逻辑只看 <img>，
    拿不到校徽，卡片只能退回首字方块；
  · 上海交大的页头（连同 LogoWhite.png）整个由 headersy.js 的 document.writeln
    注入，正则把注入的字符串当 HTML 解析才能找到它；
  · 大连交大的校徽藏在外部 CSS 的 .logo{ background:url(../img/logo.png) } 里，
    HTML 里一个字都搜不到；
  · njust 的首页对爬虫返回空壳 202、cucn 是个 Vue SPA 壳 —— 它们都**有效重定向
    到了真实学校**，只是落地页反爬/是壳。降级检测**刻意不碰**它们（打成 blocked
    会丢掉有效跳转），只认无歧义的拦截页：ehall.blcu.edu.cn 的「无感知访问」
    WAF 挑战页、「没有找到站点」停靠页、「备案」拦截页、「404 Not Found」软 404。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from update import (  # noqa: E402
    CSS_WEAK_MIN,
    SVG_WEAK_MIN,
    degraded_reason,
    parse_page,
    save_inline_svg,
)

FAILED = []


def check(name, cond, extra=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {extra}")
        FAILED.append(name)


# ==================== degraded_reason ====================
print("\n[degraded_reason] 只认无歧义的拦截页，不误伤真高校")

check("停靠页「没有找到站点」",
      degraded_reason("<html><title>没有找到站点</title></html>", "没有找到站点"))
check("备案拦截页", degraded_reason("<html><title>备案</title><body>网站备案</body></html>", "备案"))
check("WAF 挑战页标题「无感知访问」（ehall.blcu）",
      degraded_reason("<html><title>无感知访问</title></html>", "无感知访问"))
check("软 404「404 Not Found」",
      degraded_reason("<html><title>404 Not Found</title><body></body></html>", "404 Not Found"))
check("阿里云 WAF 挑战页（靠代码特征认，标题未必稳）",
      degraded_reason('<html><head><title>x</title></head><body><script>var _0x12ab=1;</script>'
                      + "长文本" * 500 + "</body></html>", "x"))

# ★ 关键回归：真高校的落地页常常「短」（反爬空壳 / SPA 壳），
#   但它们**有效重定向到了真实学校**，绝不能打成 blocked（会丢掉有效跳转）。
check("njust 空壳 202（真高校、有效跳转）不误判 -> 保持收录",
      degraded_reason(
          '<html><head><meta content="{qqqqqq}!UBRPvucotgS5O18tiZRZ2k8RiN7a6UeNiuSeUAr7WKGaRkzRqcYdROy9'
          'iOwepkR8WUGjwbRO" /></head><body></body></html>', "") is None)
check("cucn 的 Vue SPA 壳（带真标题）不误判",
      degraded_reason('<html><head><title>南京传媒学院</title></head>'
                      '<body><div id="app"></div></body></html>', "南京传媒学院") is None)
check("正常大学首页不误判",
      degraded_reason("<html><head><title>正常大学</title></head><body>" +
                      "学校新闻内容很多很多" * 100 + "</body></html>", "正常大学") is None)
check("短但有校徽的页面不误判",
      degraded_reason("<html><head><title>奶龙大学</title></head><body>"
                      "<img src='/logo.png'/></body></html>", "奶龙大学") is None)


# ==================== parse_page ====================
print("\n[parse_page] 抓标题 / 校徽，认得出内联 SVG 校徽")

# 现场：bjmu 的校徽是 <a class="web-logo"><svg>…</svg></a>，不是 <img>
bjmu_html = ('<html><head><title>北京大学医学部</title></head><body>'
             '<a class="web-logo" href="index.htm">'
             '<svg viewBox="0 0 358 60"><path d="M0 0h358v60H0z" fill="#163479"/></svg>'
             '</a></body></html>')
title, logo_url, logo_svg, degraded = parse_page(bjmu_html, "https://www.bjmu.edu.cn/")
check("标题抓到", title == "北京大学医学部")
check("内联 SVG 校徽被选中", logo_svg.startswith("<svg"))
check("没误抓外部图片", not logo_url)
check("不被误判成降级页", degraded is None)

# 现场：sjtu 的页头由 headersy.js 的 document.writeln 注入，校徽 LogoWhite.png
# 只存在于被注入的字符串里
sjtu_html = ('<html><head><title>上海交通大学</title></head><body>'
             '<script src="/resource/assets/js/headersy.js"></script>'
             '<script>document.writeln("    <div id=\'header\' class=\'header2\'>");'
             'document.writeln("    <a class=\'logo\' href=\'/\'>'
             '<img src=\'/resource/assets/img/LogoWhite.png\' alt=\'上海交通大学\'/></a>");'
             'document.writeln("</div>");</script></body></html>')
title, logo_url, logo_svg, degraded = parse_page(sjtu_html, "https://www.sjtu.edu.cn/")
check("JS 注入的校徽被找到", "LogoWhite.png" in logo_url)
check("标题抓到", title == "上海交通大学")

# 现场：普通页面，<img class=\"logo\">，老行为不变
plain_html = ('<html><head><title>某某大学</title></head><body>'
              '<img src="/images/logo.png" alt="某某大学校徽"/>'
              '<img src="/images/news1.jpg" alt="新闻配图"/>'
              '</body></html>')
title, logo_url, logo_svg, degraded = parse_page(plain_html, "https://www.example.edu.cn/")
check("老口径 img logo 优先", logo_url.endswith("/images/logo.png"))
check("普通页不给内联 SVG（本来就没有）", not logo_svg)


# ==================== save_inline_svg ====================
print("\n[save_inline_svg] 内联 SVG 落盘时补 xmlns / 剔除危险标签")
os.makedirs("logos", exist_ok=True)

svg = ('<svg viewBox="0 0 100 40"><script>alert(1)</script>'
       '<path d="M0 0h100v40H0z" fill="#163479"/></svg>')
path = save_inline_svg(svg, "test-page-assets")
check("落盘成功", bool(path) and os.path.isfile(path))
if path:
    body = open(path, encoding="utf-8").read()
    check("补齐 xmlns（<img> 引用内联 SVG 必需）",
          'xmlns="http://www.w3.org/2000/svg"' in body)
    check("<script> 被剔除", "<script" not in body)
    os.remove(path)

check("非 SVG 开头的内容拒收", not save_inline_svg("<div>not svg</div>", "test-page-assets"))
check("空内容拒收", not save_inline_svg("", "test-page-assets"))


# ==================== 阈值自检 ====================
print("\n[阈值自检] 权重门槛和打分口径保持一致")
check("CSS_WEAK_MIN 低于 icon 权重（弱候选不能顶掉旧口径）", CSS_WEAK_MIN >= 5)
check("SVG_WEAK_MIN 高于纯尺寸权重（光有宽高不够）", SVG_WEAK_MIN > 3)


print()
if FAILED:
    print(f"❌ {len(FAILED)} 个用例失败：{FAILED}")
    sys.exit(1)
print("✅ 全部通过")
