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

export default { meta, sites, statusOptions, jumpOptions }
