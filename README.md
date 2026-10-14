# 奶龙大学导航 · All of Milkdragons

把 `result.json` 里抓到的「奶龙大学 / 奶蛙大学」系列仿冒域名渲染成一面**暖黄色卡片墙**，
支持按**网址**和**学校名称**搜索，部署在 GitHub Pages 上，**数据每天自动刷新一次**。

线上地址：<https://null-bytepointer.github.io/all-of-milkdragons/>

---

## 一句话数据流

```
update.py            DNS 探测 + HTTP 跳转追踪 + 标题/校徽抓取
   ↓                  （每天 03:10 北京时间由 GitHub Actions 跑）
result.json          ┐
logos/               ├─ 抓取产物，提交进仓库
analyze_logos.py     ┘
   ↓
logo_tones.json      每张校徽的明暗体检结果（白 logo 要换深色底板）
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
├── analyze_logos.py        校徽明暗体检 -> logo_tones.json
├── result.json             抓取结果（每日刷新，入库）
├── logos/                  校徽原图（每日刷新，入库）
├── logo_tones.json         校徽体检结果（每日刷新，入库）
├── requirements.txt        Python 依赖
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

### 换自定义域名 / 换仓库名

项目站点默认挂在 `/<repo>/` 子路径下，所以 `vite.config.js` 里的 `base` 是
`/all-of-milkdragons/`。如果要改成根路径站点（自定义域名），构建时设 `BASE_PATH=/`：

```bash
BASE_PATH=/ npm run build
```

## 设计说明（为什么长这样）

* **暖黄配色**：主色蜂蜜金 `#E9A93A`，底色暖奶油 `#FFF6E2`，正文用暖棕而不是纯黑；
  阴影也带暖棕色调。所有颜色集中在 `src/styles/tokens.css` 的三层令牌里，组件里不写死 hex。
* **校徽用整卡宽的横条托盘**：抓下来的校徽**宽高比中位数 ≈ 3.7**，绝大多数是「校名横排
  字标」，塞进方形缩略图会小到看不清。
* **6 成校徽给了深色底板**：抓到的校徽里有 52/86 是「白色 logo + 透明底」（站点导航栏的
  白色版本），放在白卡片上等于隐形。`analyze_logos.py` 预先体检每张图，`logoLight` 为真
  的换深暖棕托盘。
* **打不开的域名不隐藏**：24 个失效域名照样上墙，只是降级成虚线边框 + 灰度校徽 +
  红色状态徽章，状态徽章写明 `HTTP 403` / `请求超时` 这类具体原因。
* **一个拉伸链接 + 一个落地链接**：卡片整体指向奶龙域名本身，右下角的小链接直接去它
  最终落地的真实站点；用「拉伸覆盖层」而不是 `<a>` 套 `<a>`。

## 无障碍

键盘 `/` 聚焦搜索框、`Esc` 清空；所有可点元素有可见焦点环；搜索命中数用 `aria-live`
播报；筛选用 `aria-pressed` 表达选中态而不是只靠颜色；遵循 `prefers-reduced-motion`。
