#!/usr/bin/env python3
"""
跳转规则的回归测试（纯函数，不联网）。

跑法：.venv/bin/python tests/test_jump_rules.py

每一个用例都对应一个**真实踩过的坑**，注释里写了当时的现场。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from update import (  # noqa: E402
    extract_next,
    interstitial_reason,
    is_sane_url,
    should_follow,
)

FAILED = []


def check(name, cond, extra=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {extra}")
        FAILED.append(name)


# ==================== interstitial_reason ====================
print("\n[interstitial_reason] 认得出中间页 / 拦截页")
check("DNSPod 拦截页",
      interstitial_reason("https://dnspod.qcloud.com/static/webblock.html?d=x.com") is not None)
check("百度首页",
      interstitial_reason("https://www.baidu.com/") is not None)
check("百度子域也算（baidu.com 后缀匹配）",
      interstitial_reason("https://top.baidu.com/board?platform=pc") is not None)
check("Microsoft 浏览器说明页",
      interstitial_reason("https://support.microsoft.com/zh-cn/internet-explorer/") is not None)
check("真实学校站点不算中间页",
      interstitial_reason("https://www.lnu.edu.cn/") is None)
check("教务系统不算中间页",
      interstitial_reason("http://111.117.146.166/eams/loginExt.action") is None)


# ==================== should_follow ====================
print("\n[should_follow] 这一跳该不该跟")
ORIGIN = "https://xn--psszg58cgv6aq83axit.work/"
BAIDU = "https://www.baidu.com/"

# 现场：东北奶龙大学.com 真的一路 301 到百度，爬虫接着跟百度首页的
#       `url: 'https://top.baidu.com/board?...'` 跳进了百度热搜，再跳进百度搜索。
check("已经站在中间页上 -> 不再跟",
      should_follow("https://top.baidu.com/board", "js_config", BAIDU, ORIGIN) is False)

# 现场：沈阳奶蛙大学.work 301 到某校教务系统，系统提示「请用 IE 打开」，
#       页面里的 `url: '.../internet-explorer-downloads'` 被当成了跳转目标，
#       卡片上就出现了 Microsoft 的帮助页。
check("弱信号 + 已经离开最初域名 -> 不跟",
      should_follow("https://support.microsoft.com/zh-cn/help/17621", "js_config",
                    "http://111.117.146.166/eams/loginExt.action", ORIGIN) is False)
check("弱信号 (body_target) 同理",
      should_follow("https://other.edu.cn/", "body_target",
                    "http://111.117.146.166/eams/loginExt.action", ORIGIN) is False)

# 正常流量：奶龙域名自己的页面上写 `location.href = config.url`
check("弱信号 + 还在最初域名上 -> 跟",
      should_follow("https://www.lnu.edu.cn/", "js_config", ORIGIN, ORIGIN) is True)
check("弱信号 + 已在 .edu.cn 上 -> 不跟（别被拖进 SSO 认证链）",
      should_follow("https://sso.other.edu.cn/", "js_config",
                    "https://www.lnu.edu.cn/", ORIGIN) is False)
# meta / js_location 是「显式跳转」，允许跨域继续
check("显式跳转 (meta) + 已经跨域 -> 仍然跟",
      should_follow("https://www.lnu.edu.cn/", "meta",
                    "https://www.lnu.edu.cn/", ORIGIN) is True)
check("空目标 -> 不跟", should_follow("", "meta", ORIGIN, ORIGIN) is False)


# ==================== is_sane_url ====================
print("\n[is_sane_url] 是不是一个能访问的网页地址")
# 现场：这两个地址是从**已损坏的 HTML** 里抠出来的，跟着走只会 404
check("拒绝 %3E 编码的 HTML 片段",
      is_sane_url("https://www.hkust-gz.edu.cn/%3ELocation%3C/a%3E%3C/li%3E%3Cli%20id=") is False)
check("拒绝解出来带花括号/空格的模板残渣",
      is_sane_url("https://www.polyu.edu.hk/:%20%7B%20%20%20%20/") is False)
# 现场：外链的字体 CSS 被当成了跳转目标
check("拒绝外链 CSS",
      is_sane_url("https://cdn.amoe.cc/web-static/public/font/misans/misans.css") is False)
check("拒绝外链字体",
      is_sane_url("https://x.com/a/font.woff2") is False)
check("拒绝图片",
      is_sane_url("https://x.com/img/logo.png") is False)
check("接受普通学校地址",
      is_sane_url("https://www.lnu.edu.cn/") is True)
check("接受带查询串的地址（百度搜索里有 %20，不该被误杀）",
      is_sane_url("https://www.baidu.com/s?wd=%E4%B9%9F%20%E5%A5%BD") is True)
check("接受教务系统",
      is_sane_url("http://111.117.146.166/eams/loginExt.action") is True)


# ==================== extract_next ====================
print("\n[extract_next] 从页面里挖跳转目标")

# 1) 最常见的形式，必须还能挖出来
html_loc = '<script>window.location.href = "https://www.lnu.edu.cn/";</script>'
check("location.href 字面量",
      extract_next(html_loc, "https://x.top/")[0] == "https://www.lnu.edu.cn/")

# 2) `var cfg = { url: '...' }; location.href = cfg.url;`
#    当初就是为了修这个才加的 js_config，别改回去
html_cfg = ("<script>var config = { url: 'https://www.jou.edu.cn/' };"
            "function go(){ location.href = config.url; }</script>")
check("配置对象 url + location.href = config.url",
      extract_next(html_cfg, "https://x.top/")[0] == "https://www.jou.edu.cn/")

# 3) ★ 回归：<link href="..."> 是外链静态资源，不是跳转
html_link = ('<html><head><link rel="stylesheet" '
             'href="https://fonts.googleapis.com/css?family=Nunito"></head>'
             '<body>奶龙大学</body></html>')
check("<link href> 外链字体 CSS 不能被当成跳转",
      extract_next(html_link, "https://x.top/")[0] is None)

# 4) ★ 回归：带 .css 的配置值也不认
html_cfg_css = "<script>var o = { url: 'https://cdn.x.com/a/misans.css' };</script>"
check("配置里的 .css 地址不能被当成跳转",
      extract_next(html_cfg_css, "https://x.top/")[0] is None)

# 5) ★ 回归：损坏 HTML 抠出来的乱码地址
html_bad = '<script>var a="location";</script><p>https://www.polyu.edu.hk/: {</p>'
check("乱码地址不能被当成跳转",
      extract_next(html_bad, "https://x.top/")[0] is None)

# 6) meta refresh 仍然可用
html_meta = '<meta http-equiv="refresh" content="0;url=https://www.upc.edu.cn/">'
check("meta refresh", extract_next(html_meta, "https://x.top/")[0] == "https://www.upc.edu.cn/")


print()
if FAILED:
    print(f"❌ {len(FAILED)} 个用例失败：{FAILED}")
    sys.exit(1)
print("✅ 全部通过")
