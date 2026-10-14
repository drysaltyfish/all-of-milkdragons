<script setup>
/**
 * 单张站点卡片。
 *
 * 卡片上只有三层信息：真实校名（抓不到就用域名里的奶龙校名）、奶龙域名、落地地址。
 * 结构上只用「一个拉伸的主链接 + 一个独立的落地链接」，
 * 避免 <a> 套 <a> 的非法嵌套。
 */
import { computed } from 'vue'
import SiteLogo from './SiteLogo.vue'
import SiteBadges from './SiteBadges.vue'
import QueryHighlight from './QueryHighlight.vue'

const props = defineProps({
  site: { type: Object, required: true },
  query: { type: String, default: '' },
})

const offline = computed(() => props.site.status === 'offline')
/** 标题是「退回」来的（没抓到真实站点标题），换个视觉语气 */
const derived = computed(() => !props.site.pageTitle)

const primaryAria = computed(() =>
  offline.value
    ? `${props.site.displayName} ${props.site.domain}（${props.site.statusLabel}）`
    : `打开 ${props.site.displayName} ${props.site.domain}`,
)

const targetLabel = computed(() => props.site.targetHost || props.site.targetUrl)
</script>

<template>
  <article class="card" :class="{ 'card--offline': offline }">
    <!-- 拉伸整卡的主链接：奶龙域名本身 -->
    <a
      class="card__stretch"
      :href="site.url"
      target="_blank"
      rel="noopener noreferrer"
      :aria-label="primaryAria"
    ></a>

    <SiteLogo :site="site" />

    <div class="card__ident">
      <h3
        class="card__title"
        :class="{ 'card__title--derived': derived }"
        :title="derived ? '没抓到真实站点标题，这里显示域名中的校名' : site.pageTitle"
      >
        <QueryHighlight :text="site.displayName" :query="query" />
      </h3>
      <p class="card__domain"><QueryHighlight :text="site.domain" :query="query" /></p>
    </div>

    <footer class="card__foot">
      <a
        v-if="site.hasDistinctTarget"
        class="card__target"
        :href="site.targetUrl"
        target="_blank"
        rel="noopener noreferrer"
        :title="`直接访问落地站点 ${site.targetUrl}`"
      >
        <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" focusable="false">
          <path
            d="M6 3.5h6.5V10M12.5 3.5 4 12"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        <span class="card__target-host"><QueryHighlight :text="targetLabel" :query="query" /></span>
      </a>
      <span v-else class="card__target card__target--none">本站页面</span>

      <SiteBadges :site="site" />
    </footer>
  </article>
</template>

<style scoped>
.card {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: var(--space-3);
  min-height: 12rem;
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-xs);
  transition:
    transform var(--dur-base) var(--ease-out),
    box-shadow var(--dur-base) var(--ease-out),
    border-color var(--dur-base) var(--ease-out);
}

.card:hover {
  transform: translateY(-3px);
  border-color: var(--color-border-strong);
  box-shadow: var(--shadow-md);
}

/* 键盘焦点落在拉伸链接上，视觉上等价于整卡获得焦点 */
.card:has(.card__stretch:focus-visible) {
  border-color: var(--color-focus);
  box-shadow: var(--shadow-md);
}

.card__stretch {
  position: absolute;
  inset: 0;
  z-index: 0;
  border-radius: inherit;
}

.card__stretch:focus-visible {
  outline: 3px solid var(--color-focus);
  outline-offset: 2px;
}

.card__ident {
  min-width: 0;
  flex: 1 1 auto;
}

.card__title {
  font-size: var(--text-lg);
  font-weight: 600;
  /* 标题最多两行，避免长校名把卡片撑歪 */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 退回标题：轻一点、斜一点，一眼能看出「这不是抓到的名字」 */
.card__title--derived {
  font-family: var(--font-body);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-soft);
}

.card__domain {
  margin-top: var(--space-1);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  line-height: 1.45;
  color: var(--color-primary-text);
  word-break: break-all;
}

.card__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  /* 不允许换行：落地地址自己省略号收窄，徽章永远待在右下角。
     否则同一行卡片会因为换行与否长得不一样。 */
  flex-wrap: nowrap;
}

.card__target {
  /* 浮在拉伸链接之上，这样卡片里的第二个链接点得到 */
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  flex: 1 1 auto;
  min-width: 0;
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--color-text-soft);
  /* 落地地址只占一行，长了就省略号，绝不挤走右边的徽章 */
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color var(--dur-fast) var(--ease-out);
}

.card__target-host {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

a.card__target:hover {
  color: var(--color-primary-strong);
  text-decoration: underline;
}

.card__target--none {
  font-style: italic;
  font-weight: 500;
  color: var(--color-text-soft);
}

/* ---------- 打不开的卡片：降级但不隐藏 ---------- */
.card--offline {
  border-style: dashed;
  background: var(--color-surface-sunken);
}

.card--offline .card__title:not(.card__title--derived) {
  color: var(--color-text-soft);
}

.card--offline .card__domain {
  color: var(--color-text-soft);
}

.card--offline:hover {
  transform: none;
}
</style>
