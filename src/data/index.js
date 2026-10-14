/**
 * 数据层 —— 组件与数据的唯一接口。
 *
 * 组件不 import `sites.json`，只 import 这里导出的成品；
 * 以后换数据来源（换 JSON、改接口、走 fetch）只需要改这个文件。
 *
 * `sites.json` 由 `npm run data` 从 result.json + logos/ 生成，不入库。
 */
import payload from './sites.json'

/** 生成信息：日期、来源、总量、可访问/不可访问统计 */
export const meta = {
  generatedAt: payload.generatedAt,
  source: payload.source,
  total: payload.total,
  ...payload.stats,
}

/** 筛选器选项（带静态计数），由数据层给出，组件不硬编码枚举 */
export const statusOptions = [
  { value: 'all', label: '全部', count: payload.total },
  ...payload.facets.status,
]

export const jumpOptions = [
  { value: 'all', label: '全部', count: payload.total },
  ...payload.facets.jumpType,
]

export const jumpTypeLabels = payload.jumpTypeLabels
export const jumpTypeDescriptions = payload.jumpTypeDescriptions

/**
 * 「投稿没收录的域名」弹窗的全部文案与链接。
 *
 * ★ 放这里而不是 scripts/build-data.mjs：那份文案是**由数据推导出来的**
 *   （HTTP 403 -> 「拒绝访问」这种映射），这里则是与抓取结果无关的静态说明，
 *   属于「数据层」而不是「生成物」。组件依旧只吃 props，不硬编码任何一句话。
 *
 * 文案面向没写过代码的人：不出现 issue / PR / pending / approved 这类词，
 * 只说「提交」「机器人」「等结果」。
 */
export const contribute = {
  repo: 'https://github.com/drysaltyfish/all-of-milkdragons',
  // GitHub Issue Form 不支持 URL 预填字段，所以按钮只能做到「打开表单」，
  // 访客仍需自己把域名填进那一个框里。
  formUrl:
    'https://github.com/drysaltyfish/all-of-milkdragons/issues/new?template=report-domain.yml',
  /** 页头按钮旁边的一句话说明 */
  hint: '机器人只扫「奶龙 / 奶蛙 + 大学」这类模板拼得出来的域名，拼不出来的靠大家投稿。',
  buttonLabel: '投稿没收录的域名',
  title: '投稿一个奶龙域名',
  intro: [
    '自动收录是机器人按固定模板扫出来的：前缀 + 奶龙或奶蛙 + 大学 + 后缀，一共五万多个。',
    '像「百奶宫.site」这种模板拼不出来的，机器人永远扫不到，只能靠人投稿。',
  ],
  /** 什么域名能收录 —— 这是「具体要求」 */
  requirementsTitle: '什么域名能收录',
  requirements: [
    {
      title: '域名真实存在',
      detail: '能解析、能打开。刚注册还没生效的，过两天再投。',
    },
    {
      title: '确实跳到一所学校的官网',
      detail: '这是唯一的硬要求。停放的、跳广告的、跳搜索引擎或短视频的，都不会收录。',
    },
    {
      title: '还没被收录',
      detail: '先在页面上的搜索框里搜一下域名，搜得到就不用投了。',
    },
    {
      title: '不是模板拼得出来的',
      detail: '比如「北京奶龙大学.com」机器人自己会扫，投了会被直接退回。',
    },
    {
      title: '有一个 GitHub 账号',
      detail: '免费注册，但账号要注册满 30 天；同一个账号每天最多投 5 条。',
    },
  ],
  /** 怎么投稿 —— 这是「具体方法」 */
  stepsTitle: '怎么投稿',
  steps: [
    {
      title: '先在页面搜一下',
      detail: '确认这个域名还没在列表里。',
    },
    {
      title: '打开投稿表单',
      detail: '点下面的按钮会跳到 GitHub。没有账号的话先注册一个，免费。',
    },
    {
      title: '在「域名」那一栏填域名',
      detail: '只填域名本身，例如 百奶宫.site。不要带 https://，也不要带斜杠后面的路径。',
    },
    {
      title: '勾上确认框，点提交',
      detail: '表单里有一句「我确认这个域名会跳转到一所真实学校的官网」，勾上它，然后点 Submit new issue。',
    },
    {
      title: '等结果',
      detail: '机器人每天会访问一次。通常一天内就有结论。',
    },
  ],
  /** 提交之后会怎样 —— 把三种结局讲清楚，省得访客一头雾水 */
  outcomesTitle: '提交之后会怎样',
  outcomes: [
    {
      kind: 'ok',
      title: '真的跳到了学校官网',
      detail: '自动收录，出现在列表里；卡片右下角会多一个「网友投稿」的小标签，你提交的那条也会自动关闭。',
    },
    {
      kind: 'wait',
      title: '跳到了别的地方',
      detail: '先挂在待复核里等人工看一眼 —— 有些学校官网用的不是教育域名，机器不敢自己拍板。',
    },
    {
      kind: 'bad',
      title: '打不开，或者是个拦截页',
      detail: '会被退回，并在你的提交下面写明原因。修好后可以重新投。',
    },
  ],
  notes: [
    '往页面灌垃圾没有用：域名必须真的落到学校官网，才可能出现在列表里。',
    '校徽是从目标站点自己抓的，不是我们画的。',
    '已经收录但暂时打不开的域名不用投稿 —— 它们本来就留在墙上，连续 3 天打不开才会被移除。',
  ],
  ctaLabel: '去 GitHub 投稿',
  ctaNote: '会跳到 GitHub，需要一个账号',
}

/**
 * 预拼一个小写检索串，避免每次按键都对 165 条记录重复做 join/lowercase。
 * 覆盖：校名（域名里的奶龙校名）、抓到的页面标题、奶龙域名、punycode、落地域名。
 */
export const sites = payload.sites.map((site) => ({
  ...site,
  searchText: [
    site.schoolName,
    site.pageTitle,
    site.domain,
    site.ascii,
    site.targetHost,
  ]
    .filter(Boolean)
    .join('\n')
    .toLowerCase(),
}))

export default { meta, sites, statusOptions, jumpOptions, contribute }
