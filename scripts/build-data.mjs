#!/usr/bin/env node
/**
 * 数据构建脚本 —— 把抓取产物 (result.json + logos/) 转换成前端消费的静态数据。
 *
 * 设计原则：**component 与 data 分离**
 *   · 组件只消费 `src/data/sites.json`，完全不知道抓取/跳转/图片探测的存在；
 *   · 所有清洗、枚举、文案映射都收敛在本脚本里，组件不再做数据整形；
 *   · 生成物 (src/data/sites.json、public/logos/) 不入库，由 `npm run data` 复现。
 *
 * 用法：npm run data
 */
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const SOURCE_JSON = join(ROOT, 'result.json')
const SOURCE_LOGOS = join(ROOT, 'logos')
/** 校徽明暗体检结果，由 analyze_logos.py 生成（Node 这边不做图片解码） */
const LOGO_TONES_JSON = join(ROOT, 'logo_tones.json')
const OUT_JSON = join(ROOT, 'src', 'data', 'sites.json')
const OUT_LOGOS = join(ROOT, 'public', 'logos')

/** 跳转类型枚举：值与 result.json 的 jump_type 对齐，文案在这里单点维护。 */
const JUMP_TYPES = [
  {
    value: 'none',
    label: '无跳转',
    description: '域名自己就是一个页面，没有再次跳转',
  },
  {
    value: 'direct',
    label: '直达跳转',
    description: 'HTTP 3xx 直接跳到目标站点',
  },
  {
    value: 'delayed',
    label: '二级跳转',
    description: '靠 meta refresh / JS location 这类前端手段再跳一次',
  },
]

/** 状态枚举：online = 最终能拿到 2xx/3xx，offline = 其余情况。 */
const STATUSES = [
  { value: 'online', label: '可访问' },
  { value: 'offline', label: '打不开' },
]

/** 抓取侧用的错误码 -> 中文说明。 */
const ERROR_LABELS = {
  conn_error: '无法建立连接',
  timeout: '请求超时',
  no_dns: '域名没有解析',
  too_many_redirects: '跳转次数过多',
}

/** HTTP 状态码 -> 一句话解释。 */
const HTTP_HINTS = {
  400: '请求被拒绝',
  401: '需要登录',
  403: '拒绝访问',
  404: '页面不存在',
  405: '方法不被允许',
  406: '不接受该请求',
  412: '前置条件校验失败',
  429: '请求过于频繁',
  500: '源站内部错误',
  502: '网关错误',
  503: '服务不可用',
  504: '网关超时',
  522: '源站连接超时',
  526: '证书校验失败',
}

/** Python 侧的 requests 异常名 -> 中文说明（别把 `page:ConnectionError` 直接甩给用户）。 */
const PAGE_ERROR_LABELS = {
  ConnectionError: '连接失败',
  ConnectTimeout: '连接超时',
  ReadTimeout: '读取超时',
  Timeout: '请求超时',
  TooManyRedirects: '跳转次数过多',
  SSLError: '证书错误',
  InvalidURL: '地址不合法',
  MissingSchema: '地址缺少协议',
  ChunkedEncodingError: '响应传输中断',
  ContentDecodingError: '内容解码失败',
}

/** 把 result.json 里的 error 字段翻成人话。 */
function describeError(raw) {
  if (!raw) return ''
  if (ERROR_LABELS[raw]) return ERROR_LABELS[raw]

  const http = String(raw).match(/^page:http_(\d{3})$/)
  if (http) return `HTTP ${http[1]}`

  const page = String(raw).match(/^page:(.+)$/)
  if (page) return PAGE_ERROR_LABELS[page[1]] || '详情页抓取异常'

  return String(raw)
}

/**
 * 状态 + 徽章文案的**唯一**来源。
 *
 * 判定只看 HTTP 终态码：2xx/3xx 就算可访问。
 * `error` 字段不能用来判死活 —— 它同时承载了两类完全不同的失败：
 *   · 「站点自己连不上」（conn_error / timeout / page:http_403 …）
 *   · 「站点 200 了，但跳转目标或详情页抓取失败」（那 40 个 error 非空、
 *      final_status=200 的域名就是这么来的）
 * 早先把 error 当死活的判据，结果 40 张卡片出现「卡片降级成打不开、徽章却写可访问」
 * 的自相矛盾。现在统一在这里出，标签和 status 不可能再打架。
 *
 * 徽章空间有限，所以拆成「短标签 + 详细说明」：
 * 标签进徽章（`HTTP 403`），说明进 title / aria-label。
 */
/** update.py 里连续失联多少天才真的移除（要和 RETENTION_DAYS 保持一致）。 */
const RETENTION_DAYS = 3

/**
 * 「已失联 N 天」。
 *
 * update.py 对失联的域名不立刻删：先降级成打不开继续挂着，连着 3 天都回不来
 * 才从墙上移除。把这件事写进说明里，用户才知道这张卡片为什么还在、
 * 以及它什么时候会消失。
 */
function downInfo(row) {
  const since = String(row.down_since || '')
  if (!since) return ''
  const ms = Date.parse(since)
  if (!Number.isFinite(ms)) return `自 ${since} 起失联`
  const days = Math.floor((Date.now() - ms) / 86400000)
  if (days <= 0) return `今天起失联，连续 ${RETENTION_DAYS} 天不恢复就移除`
  return `已失联 ${days} 天，满 ${RETENTION_DAYS} 天不恢复就移除`
}

function statusBadgeOf(row) {
  const raw = String(row.error || '')
  const code = toNumber(row.final_status)
  const down = downInfo(row)

  // ★ 落点是「中间页 / 拦截页」：DNSPod 的域名拦截页、百度首页、IE 下载说明页……
  //   不管 HTTP 状态码是多少，这个奶龙域名都没有指向真正的校园站点，
  //   所以不能算「可访问」，也不该把别人家的标题当成校名。
  //   说明来自 update.py 的 INTERSTITIAL_HOSTS。
  if (row.blocked) {
    const detail = `没有指向真正的校园站点 —— ${String(row.blocked)}`
    return {
      status: 'offline',
      label: '无有效跳转',
      detail: down ? `${detail}（${down}）` : detail,
    }
  }

  if (code && code >= 200 && code < 400) {
    // 站点本身是通的，但抓详情/跳转目标时出过问题，如实写在说明里
    const detail = raw
      ? `HTTP ${code}，但页面详情或跳转目标抓取失败（${describeError(raw)}）`
      : `抓取时返回 HTTP ${code}`
    return { status: 'online', label: '可访问', detail }
  }

  // 有状态码就让状态码说话，比「连接失败」这种笼统说法准确
  if (code) {
    const hint = HTTP_HINTS[code] || '异常状态码'
    const extra = describeError(raw)
    // 别写成「HTTP 403 · 拒绝访问（HTTP 403）」
    const suffix = extra && extra !== `HTTP ${code}` ? `（${extra}）` : ''
    const tail = down ? ` · ${down}` : ''
    return {
      status: 'offline',
      label: `HTTP ${code}`,
      detail: `HTTP ${code} · ${hint}${suffix}${tail}`,
    }
  }

  const label = describeError(raw) || '无响应'
  const base = raw ? `${label}（没有拿到 HTTP 状态码）` : '请求没有拿到任何响应'
  return {
    status: 'offline',
    label,
    detail: down ? `${base} · ${down}` : base,
  }
}

/**
 * 抓回来的「标题」里有一些是服务器的默认报错页，不是站点名。
 * 命中这些模式就当作没抓到标题，卡片回退到域名里的校名。
 */
const NOISE_TITLE_PATTERNS = [
  /^4\d\d\b/,
  /^5\d\d\b/,
  /^error\b/i,
  /^not found$/i,
  /nginx/i,
  /^apache/i,
  /^iis\b/i,
  /^index of\b/i,
  /^default (web )?site/i,
  /^没有找到站点$/,
  /^无法访问/,
  /^页面不存在/,
  /^站点未(绑定|找到|开通)/,
  /^域名(未绑定|不存在|已过期|已暂停)/,
]

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'))
}

function toNumber(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

/** `中国奶龙大学.top` -> `中国奶龙大学`（去掉最后一段后缀，中文域名也是一个 label）。 */
function schoolNameFromDomain(domain) {
  const labels = String(domain).split('.')
  return labels.length > 1 ? labels.slice(0, -1).join('.') : String(domain)
}

function hostOf(url) {
  if (!url) return ''
  try {
    return new URL(url).host
  } catch {
    return ''
  }
}

/** 清掉标题两端的装饰符（`==欢迎访问苏州大学网站==`）和多余空白。 */
function cleanTitle(raw) {
  const text = String(raw || '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^[=\-–—|·]+/, '')
    .replace(/[=\-–—|·]+$/, '')
    .trim()
  if (!text) return ''
  if (NOISE_TITLE_PATTERNS.some((pattern) => pattern.test(text))) return ''
  return text
}

function normalize(row, tones) {
  const domain = String(row.domain || '').trim()
  const ascii = String(row.ascii || '').trim()
  const pageTitle = cleanTitle(row.title)
  const targetUrl = String(row.final_url || '').trim()
  const httpStatus = toNumber(row.final_status)
  const logo = row.logo_path ? String(row.logo_path).replace(/^\.?\//, '') : ''
  const tone = tones[logo] || null
  const schoolName = schoolNameFromDomain(domain)
  // ★ 状态与徽章文案必须来自同一个判断，否则会出现「状态=打不开、徽章=可访问」
  //   这种自相矛盾的卡片：error 字段既记录「站点本身连不上」，也记录
  //   「站点 200 了但跳转目标/详情页抓取失败」，两者不能混为一谈。
  const badge = statusBadgeOf(row)

  return {
    id: ascii || domain,
    /** 奶龙域名（保持中文，直接给用户看） */
    domain,
    /** punycode 形式，方便复制/排查 */
    ascii,
    /** 域名里的奶龙校名，例如「北京奶龙大学」 */
    schoolName,
    /** 抓到的目标站点标题，例如「北京理工大学」——真正的「学校名称」 */
    pageTitle,
    /** 卡片标题：优先用真实校名，抓不到就退回域名里的奶龙校名 */
    displayName: pageTitle || schoolName,
    /** 卡片主链接：奶龙域名本身 */
    url: `https://${domain}/`,
    /** 最终落地地址 */
    targetUrl,
    targetHost: hostOf(targetUrl),
    /** 只有落地地址和域名不是一回事时才值得展示 */
    hasDistinctTarget: Boolean(targetUrl) && hostOf(targetUrl) !== ascii,
    logo,
    /** 校徽整体偏白（白 logo + 透明底），前端要给它换深色底板 */
    logoLight: tone?.tone === 'light',
    /** 校徽宽高比，>1 是横排字标 */
    logoAspect: tone?.aspect ?? null,
    jumpType: JUMP_TYPES.some((t) => t.value === row.jump_type) ? row.jump_type : 'none',
    status: badge.status,
    httpStatus,
    statusLabel: badge.label,
    /** 徽章放不下的完整说明，进 title / aria-label */
    statusDetail: badge.detail,
    /** 落到中间页 / 拦截页的原因（空串表示没有），前端只用来做说明 */
    blockedReason: row.blocked ? String(row.blocked) : '',
    /** 第一次失联的日期（空串表示当前可访问）。失联满 RETENTION_DAYS 天会被 update.py 移除 */
    downSince: row.down_since ? String(row.down_since) : '',
    /** 最后一次访问成功的日期 */
    lastOk: row.last_ok ? String(row.last_ok) : '',
    latency: toNumber(row.latency_s),
    ips: String(row.ips || '')
      .split(',')
      .map((v) => v.trim())
      .filter(Boolean),
  }
}

function main() {
  if (!existsSync(SOURCE_JSON)) {
    throw new Error(`找不到数据源：${SOURCE_JSON}`)
  }

  const rows = readJson(SOURCE_JSON)
  if (!Array.isArray(rows)) throw new Error('result.json 的顶层结构应该是数组')

  // 校徽体检结果是可选的：没有也能构建，只是统一按深色 logo 处理
  let tones = {}
  if (existsSync(LOGO_TONES_JSON)) {
    tones = readJson(LOGO_TONES_JSON)
  } else {
    console.warn('[data] 没有 logo_tones.json，校徽将统一按深色处理（可运行 analyze_logos.py 生成）')
  }

  const sites = rows
    .map((row) => normalize(row, tones))
    .sort((a, b) => a.domain.localeCompare(b.domain, 'zh-Hans-CN'))

  // ---- 校徽：只搬运真正被引用的文件，并清掉上一次的残留 ----
  rmSync(OUT_LOGOS, { recursive: true, force: true })
  mkdirSync(OUT_LOGOS, { recursive: true })

  let copied = 0
  for (const site of sites) {
    if (!site.logo) continue
    const from = join(ROOT, site.logo)
    if (!existsSync(from)) {
      site.logo = ''
      continue
    }
    const to = join(OUT_LOGOS, site.logo.replace(/^logos\//, ''))
    copyFileSync(from, to)
    copied += 1
  }

  const nameCounts = (pick) =>
    sites.reduce((acc, site) => {
      const key = pick(site)
      acc[key] = (acc[key] || 0) + 1
      return acc
    }, {})

  const payload = {
    generatedAt: statSync(SOURCE_JSON).mtime.toISOString().slice(0, 10),
    source: 'result.json',
    total: sites.length,
    stats: {
      online: sites.filter((s) => s.status === 'online').length,
      offline: sites.filter((s) => s.status === 'offline').length,
      withLogo: sites.filter((s) => s.logo).length,
    },
    facets: {
      status: STATUSES.map((s) => ({ ...s, count: sites.filter((x) => x.status === s.value).length })),
      jumpType: JUMP_TYPES.map((j) => ({ ...j, count: sites.filter((x) => x.jumpType === j.value).length })),
    },
    jumpTypeLabels: Object.fromEntries(JUMP_TYPES.map((j) => [j.value, j.label])),
    jumpTypeDescriptions: Object.fromEntries(JUMP_TYPES.map((j) => [j.value, j.description])),
    jumpTypeCounts: nameCounts((s) => s.jumpType),
    sites,
  }

  mkdirSync(dirname(OUT_JSON), { recursive: true })
  writeFileSync(OUT_JSON, `${JSON.stringify(payload, null, 2)}\n`, 'utf8')

  const size = (statSync(OUT_JSON).size / 1024).toFixed(1)
  console.log(
    `[data] ${sites.length} 个域名（可访问 ${payload.stats.online} / 打不开 ${payload.stats.offline}），` +
      `校徽 ${copied} 张 -> public/logos/，数据 ${size} KB -> src/data/sites.json`,
  )
  if (readdirSync(SOURCE_LOGOS).length !== copied) {
    console.log(`[data] 提示：logos/ 里有 ${readdirSync(SOURCE_LOGOS).length - copied} 个未被引用的文件，已忽略。`)
  }
}

main()
