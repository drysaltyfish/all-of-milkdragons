# 奶龙大学导航 · All of Milkdragons

把 `result.json` 里抓到的「奶龙大学 / 奶蛙大学」系列仿冒域名渲染成一面**暖黄色卡片墙**，
支持按**网址**和**学校名称**搜索，部署在 GitHub Pages 上，**数据每天自动刷新一次**。

线上地址：<https://drysaltyfish.github.io/all-of-milkdragons/>

---

## 一句话数据流

```
update.py            DNS 探测 + HTTP 跳转追踪 + 标题/校徽抓取
   ↓                  （每天 03:10 北京时间由 GitHub Actions 跑）
result.json          ┐
logos/               ├─ 抓取产物，提交进仓库
   ↓                 ┘
process_logos.py     校徽后处理：去底色 / 裁空白 / 限尺寸（原地覆盖 logos/）
   ↓
analyze_logos.py     校徽明暗体检 -> logo_tones.json
   ↓
prune_logos.py       删掉不再被引用的校徽，防止仓库无限膨胀
   ↓
scripts/build-data.mjs   清洗 / 归一化 / 枚举 / 文案映射
   ↓
src/data/sites.json  ┐  构建产物，不入库
public/logos/        ┘
   ↓
src/data/index.js    数据层：组件唯一的入口
   ↓
src/components/*.vue 组件层：只吃 props，不碰抓取细节
```

## 目录结构

```
├── update.py               抓取脚本（DNS / HTTP / 标题 / 校徽）
├── const.py                域名拼装用的词表与请求头
├── process_logos.py        校徽去底色 + 裁空白 + 限尺寸
├── analyze_logos.py        校徽明暗体检 -> logo_tones.json
├── prune_logos.py          清理未被引用的校徽
├── result.json             抓取结果（每日刷新，入库）
├── logos/                  校徽（每日刷新，入库）
├── logo_tones.json         校徽体检结果（每日刷新，入库）
├── requirements.txt        Python 依赖
├── tests/                  纯函数回归测试（不联网，CI 里抓取前先跑）
│   ├── test_jump_rules.py     跳转该不该跟 / 中间页识别 / 地址合法性
│   └── test_logo_tone.py      校徽明暗判定（位图 + SVG）
│
├── scripts/build-data.mjs  result.json -> src/data/sites.json（Node，无第三方依赖）
├── src/
│   ├── data/index.js       数据层（唯一的「数据 → 组件」接口）
│   ├── composables/        纯逻辑（搜索 / 筛选，与组件解耦）
│   ├── components/         展示组件
│   ├── styles/             设计令牌 + 基础样式 + 自托管字体
│   ├── App.vue             装配层（只做连线）
│   └── main.js
├── public/fonts/           自托管 Fredoka / Nunito（latin 子集，不依赖外部 CDN）
│
└── .github/workflows/
    ├── refresh-data.yml    每日抓取数据并提交
    └── deploy.yml          构建并发布到 GitHub Pages
```

## component 与 data 是分开的

* **数据层** `src/data/index.js` 是组件唯一的数据入口。它导出成品：站点数组、筛选项、
  统计数字，并且预先拼好 `searchText`（165 条记录不必在每次按键时重复 join/lowercase）。
  换数据来源只改这一个文件。
* **组件层** 不 `import sites.json`，也不知道「JMP 类型」「HTTP 403」这些词从哪来 ——
  文案映射全部在 `scripts/build-data.mjs` 里单点维护，随数据一起下发。
* **逻辑层** `src/composables/useSiteFilter.js` 是纯函数式的搜索 + 筛选，不依赖任何 DOM。
* 生成物（`src/data/sites.json`、`public/logos/`）不入库，`npm run data` 随时复现。

## 本地开发

```bash
npm install
npm run dev      # 会先跑 npm run data 再起 Vite
npm run build    # 产物在 dist/
npm run preview  # 预览 dist（注意带 base 路径 /all-of-milkdragons/）
```

重新抓一遍数据（需要 Python）：

```bash
python3 -m pip install -r requirements.txt
python3 update.py
python3 analyze_logos.py
```

## 部署

### 首次

1. 仓库 Settings → Pages → **Source 选 “GitHub Actions”**（不要选 branch）。
2. 推一次 `main`，`deploy.yml` 会把 `dist/` 发上去。

### 日常

| Workflow | 触发 | 干什么 |
| --- | --- | --- |
| `refresh-data.yml` | 每天 `19:10 UTC`（北京时间次日 03:10）/ 手动 | 跑 `update.py` + `analyze_logos.py`，把数据变更提交回 `main`，然后主动叫一次部署 |
| `deploy.yml` | 推到 `main` / 手动 | `npm ci` → `npm run build` → 发布到 Pages |

> **为什么要「主动叫一次部署」**：用 `GITHUB_TOKEN` 推上去的提交不会再触发 `push` 类
> workflow（GitHub 防递归），所以 `refresh-data.yml` 末尾必须显式
> `gh workflow run deploy.yml`，否则数据更新了但页面不会重新发布。

### 自定义域名 / 换仓库名（最容易白屏的地方）

站点绑在 **www.宇宙奶龙大全.space**（punycode `www.xn--15qr2q0gp9eucq780c.space`）上，
自定义域名下站点挂在**根路径**，所以 `vite.config.js` 里 `base` 的默认值是 `/`，
`public/CNAME` 里也写好了域名。

⚠️ **base 和实际路径不一致 = 整页白屏**：HTML 能返回 200，但里面引的是
`/<base>/assets/...`，路径对不上就是一片 404，JS/CSS 全加载不到，页面空白、控制台一堆红。
本仓库踩过一次：绑了自定义域名但 base 还是 `/all-of-milkdragons/`。

* 回到 GitHub Pages「项目站点」→ 构建时改回子路径：
  ```bash
  BASE_PATH=/all-of-milkdragons/ npm run build
  ```
* 换自定义域名 → 把 `public/CNAME` 改成新域名（IDN 用 punycode），base 保持 `/`。

判断是不是这个毛病，一行就够：`curl -s <站点> | grep -o 'src="[^"]*"'`，
看它要的路径和你实际部署的路径是否一致。

## 设计说明（为什么长这样）

* **暖黄配色**：主色蜂蜜金 `#E9A93A`，底色暖奶油 `#FFF6E2`，正文用暖棕而不是纯黑；
  阴影也带暖棕色调。所有颜色集中在 `src/styles/tokens.css` 的三层令牌里，组件里不写死 hex。
* **校徽用整卡宽的横条托盘**：抓下来的校徽**宽高比中位数 ≈ 3.7**，绝大多数是「校名横排
  字标」，塞进方形缩略图会小到看不清。
* **托盘的颜色跟着校徽走**：抓到的校徽里六成以上是「白色 logo + 透明底」（站点导航栏上的
  白色版本），放浅色卡片上等于隐形。`analyze_logos.py` 会给每张图做明暗体检，`logoLight`
  为真的换深暖棕托盘（`.tray--on-dark`），其余用浅托盘。**托盘是站点自己的设计**，
  和校徽图片自带的底色是两回事。
* **校徽图片自带的实色底在数据阶段就抠掉**：少数校徽是「白底/深蓝底/紫底的一整块矩形」，
  放在深色托盘上会变成一个刺眼的白/蓝色方框。`process_logos.py` 沿边缘做容差洪水填充把
  它们抠成透明。判断时**只看不透明的边缘点**，否则白字透明底的 logo 会被误判成
  「底色是白」，一洪水填充把字整个吃掉。同时它按 alpha 边界裁掉四周空白，
  并把超过 160px 高 / 640px 宽的图压回来——抓回来过 8072×1670 的 PNG。
* **打不开的域名不隐藏**：失效域名照样上墙，只是降级成虚线边框 + 灰度校徽 +
  红色状态徽章，状态徽章写明 `HTTP 403` / `请求超时` 这类具体原因。
* **死活只看 HTTP 终态码，不看 `error` 字段**。`result.json` 的 `error` 同时装了
  两类完全不同的失败：「站点自己连不上」和「站点 200 了，但跳转目标/详情页抓取失败」
  （172 条里有 40 条属于后者）。早先把 `error` 当死活判据，于是这 40 张卡片
  一边降级成「打不开」、一边徽章写着「可访问」。现在 `statusBadgeOf()` 是状态和徽章
  文案的唯一来源：2xx/3xx 即可访问，详情抓取的失败降级成 tooltip 说明。
* **一个拉伸链接 + 一个落地链接**：卡片整体指向奶龙域名本身，右下角的小链接直接去它
  最终落地的真实站点；用「拉伸覆盖层」而不是 `<a>` 套 `<a>`。

### 前端踩过的坑

* **`max-height: 100%` 在 grid 里会失效**。`.tray` 一开始写成 `display: grid;
  place-items: center`，那是一个隐式的 `auto` 行，行高由图片自己撑出来，图片上的百分比
  max-height 找不到确定参照，浏览器直接当 `none` —— 图片会冲出托盘（实测 63px 高塞在
  52px 里），整面墙的校徽高度全乱。改成 `display: flex` 后交叉轴尺寸确定，才约束得住。
* **小图不要放大**。`process_logos.py` 只缩不放：把 63px 高的小图插值到 160px 只会让
  仓库体积翻倍、画质更糊，显示尺寸本来就由 CSS 统一。
* **flex 子项的 `min-width: auto` 会把卡片撑破网格**。`.card__foot` 是一行
  `flex-wrap: nowrap` 的「落地链接 + 徽章」，它的 min-content 宽度是两者 min-content
  之和（实测 126px + 145px ≈ 279px）；卡片又默认 `min-width: auto`，于是把这个
  min-content 当成了自己的最小宽度。轨道被压到最小值（`--card-min: 17.5rem`）时，
  卡片比轨道宽出二三十像素，直接盖到右边那张卡片上 —— 实测 1280 / 1440 宽度下有
  4 对卡片重叠、16 张宽度不一致。在 `.grid__cell` 和 `.grid__cell > *` 上补
  `min-width: 0` 即可（`SiteGrid.vue`）。**排查手法**：用 CDP 量每张卡片的
  `getBoundingClientRect()` 和它所在格子的宽度，差值为正就是它；再克隆一份设
  `width: min-content` 量出归因。
* **白底 logo 的判定只看「白墨水占比」**。`analyze_logos.py` 原来要求「平均亮度 > 0.82
  且白墨水 > 0.70」，两条都要满足，结果 17 张白色字标（南方科技大学、辽宁大学、
  复旦大学、广州大学……）因为带投影/描边，白墨水占比落在 0.51~0.71、平均亮度被压到
  0.73~0.85，两条都不达标，白字被摆到了白底板上直接隐形。现在只看白墨水占比 ≥ 0.5。
  唯一的例外是**整张图完全不透明**（自带实色底，放深色板上会露出一块白方块），
  这种永远给白底板。SVG 也不能漏：Pillow 打不开 SVG，得解析 `fill` 声明，
  否则一律 `unknown` → 白底板（山东大学的 `fill: #fff` SVG 就栽在这里）。

## 抓取踩过的坑（改 `update.py` 前先看这里）

这四个坑都会表现为「页面明明有跳转，却抓不到」，而且都不报错：

1. **`Accept-Encoding` 里的 `br`**。requests/urllib3 只有在装了 `brotli` 包时才会解压
   Brotli，否则把压缩字节流原样交回来。之前请求头里写着 `br`，这些站点的 HTML 就变成
   一堆乱码二进制，标题、校徽、跳转地址全部抓不到。现在请求头只留 `gzip, deflate`。
2. **编码探测**。响应头没有 charset 时 requests 会退回 ISO-8859-1，中文站点整页乱码。
   `response_text()` 按 HTTP 头 → `<meta charset>` → `apparent_encoding` → UTF-8 逐级兜底。
3. **`location.href = config.url` 型模板**。目标地址写在配置对象里（`url: 'http://...'`），
   `location` 后面并没有字面量 URL，所以「`location.*= "..."`」和「location 附近的 URL」
   两条正则都抓不到。新增 `JS_CONFIG_RE` 兜住这种写法（并跳过指向自身 host 的
   `og:url` / canonical）。
   ⚠️ 但它**只能扫 `<script>` 里的内容**：直接扫整个 HTML 会把
   `<link href="https://fonts.googleapis.com/...">` 这种外链静态资源当成跳转目标 ——
   实测有域名被跳到了 Google Fonts 的 CSS 和 `cdn.amoe.cc` 的字体 CSS 上。
   另外 `is_sane_url()` 会拦掉静态资源后缀，以及从**已损坏的 HTML** 里抠出来的
   乱码地址（见过 `.../%3ELocation%3C/a%3E` 和 `.../:%20%7B%20%20`，
   解出来就是 `>Location</a>` 和 `: {  `）。
4. **DNS 预算**。`resolver.lifetime` 是整次解析的总预算，原来它和 `timeout` 都设成 3 秒，
   第一个 DNS 服务器一超时就吃光预算、后面的服务器根本轮不到。海外 runner 上前两跳容易抖，
   于是稳定丢掉三成域名。现在 `timeout=3 / lifetime=9`，并去掉了对境外查询会拒答的
   `114.114.114.115`。

另外：`download_logo` 用 `stream=True`，**任何提前 return 都必须关掉响应**（这里用
`with r:`），否则连接池会被占满，两百个线程一起卡死，整个抓取看起来像挂住。

### 「抓回别人家的页面」——跳转不能跟着乱跳

上面四个坑是「该抓到却没抓到」，这几个反过来：**抓到了，但抓到的是别人家网站的内部导航**。
三个现场：

| 域名 | 抓回来的东西 | 为什么 |
| --- | --- | --- |
| 东北奶龙大学.com | 百度搜索结果 | 域名真的 301 到 `www.baidu.com`，爬虫接着跟了百度首页里的 `url: 'https://top.baidu.com/board?...'`，再跟着跳进百度搜索 |
| 江苏奶蛙大学.com | DNSPod 的广告页 | 域名 302 到 `dnspod.qcloud.com/static/webblock.html`（DNSPod 的拦截页），爬虫接着逛起了 DNSPod 自己的站 |
| 沈阳奶蛙大学.work | Microsoft 的 IE 帮助页 | 域名 301 到某校教务系统，系统提示「请用 IE 打开」，页面里的 `url: '.../internet-explorer-downloads'` 被当成了跳转目标 |

收敛成两条规则（`should_follow()`，纯函数，`tests/test_jump_rules.py` 全覆盖）：

1. **已经站在已知的中间页/拦截页上就停**（`INTERSTITIAL_HOSTS`：DNSPod 拦截页、百度、
   Google、Microsoft 支持页……）。落点要是这些，就标记 `blocked`、把链接收回最后一跳
   干净的地方，并且**不抓标题也不下载校徽**（那是别人家的内容）。
2. **弱信号（`js_config` / `body_target`）只在最初那个奶龙域名自己的页面上才认**。
   它们只是页面里一个 `url: "..."` 字面量，不代表「本站在跳转」；一旦已经跨域
   （尤其是落到某个学校的教务系统），再认就会把浏览器兼容提示里的下载链接当跳转。

`meta` / `location.href = "..."` 这类**显式跳转**仍然允许跨域继续 —— 那是站点在明说
「我要去别处」。

### 「打不开」里有一半是误判

实测 34 个「打不开」里有 20 个，同一时刻用**一模一样的请求头**再发一次就是 200，
其中 6 个是彻底没拿到状态码（超时/断连）、其余是 403 / 412 / 429。

排查时先确认不是请求头的问题：把 `DEFAULT_HEADERS` 和「只带 UA」两种发法对比跑一遍，
两者结果一样，就说明跟头无关（实测确实一样）。真正的原因是**并发**：176 个奶龙域名
里一大批挂在同一个「域名停放/跳转」服务后面（单看 `15.197.162.184` 一个 IP 上就挤了
11 个），`HTTP_WORKERS = 200` 一股脑打过去，对端直接限流或者掐连接。

对策两条：`HTTP_WORKERS` 降到 48；再补一个 **[阶段 2.5] 降并发复检**（4 个线程 +
随机错峰），把「像是被限流/超时」的行重跑一遍，只有结果更好才替换。
`TRANSIENT_STATUS` 只放限流/网关抖动那类状态码 —— 404 / 400 是站点自己说的「没有」，
重试没有意义。

## 无障碍

键盘 `/` 聚焦搜索框、`Esc` 清空；所有可点元素有可见焦点环；搜索命中数用 `aria-live`
播报；筛选用 `aria-pressed` 表达选中态而不是只靠颜色；遵循 `prefers-reduced-motion`。
