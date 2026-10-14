<script setup>
/**
 * 校徽托盘。
 *
 * 两个数据事实决定了它的样子：
 *   1. 校徽中位宽高比 ≈ 3.7，绝大多数是「校名横排字标」——塞进方形缩略图会小到看不清，
 *      所以这里用整卡宽度的横条托盘；
 *   2. 有 6 成校徽是「白色 logo + 透明底」（站点导航栏的白色版本），放白底上等于隐形，
 *      所以 analyze_logos.py 会预先体检明暗，这里据 logoLight 换成深色暖棕托盘。
 *
 * 没有校徽（或加载失败）时退化成首字托盘，保证每张卡片顶部重量一致。
 */
import { computed, ref, watch } from 'vue'

const props = defineProps({
  site: { type: Object, required: true },
})

const failed = ref(false)

watch(
  () => props.site.id,
  () => {
    failed.value = false
  },
)

// 用 BASE_URL 拼，GitHub Pages 的子路径部署才不会 404
const src = computed(() =>
  props.site.logo ? `${import.meta.env.BASE_URL}${props.site.logo}` : '',
)

const initial = computed(() => (props.site.displayName || '奶').trim().charAt(0))

const showFallback = computed(() => !src.value || failed.value)
const onDark = computed(() => !showFallback.value && Boolean(props.site.logoLight))
</script>

<template>
  <div
    class="tray"
    :class="{
      'tray--fallback': showFallback,
      'tray--on-dark': onDark,
      'tray--muted': site.status === 'offline',
    }"
  >
    <img
      v-if="!showFallback"
      class="tray__img"
      :src="src"
      alt=""
      aria-hidden="true"
      loading="lazy"
      decoding="async"
      @error="failed = true"
    />
    <span v-else class="tray__initial" aria-hidden="true">{{ initial }}</span>
  </div>
</template>

<style scoped>
.tray {
  display: grid;
  place-items: center;
  width: 100%;
  height: 3.25rem;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-sunken);
  transition: filter var(--dur-base) var(--ease-out);
}

.tray__img {
  width: auto;
  height: auto;
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

/* 白色 logo 的托盘：深暖棕，对比度够又不跳出暖黄主题 */
.tray--on-dark {
  background: linear-gradient(150deg, var(--honey-700), var(--honey-900));
  border-color: var(--honey-800);
}

/* 没有校徽时的首字托盘：淡到几乎只是「有人占座」，
   让真正的校徽成为卡片上唯一抢眼的东西 */
.tray--fallback {
  background: linear-gradient(140deg, var(--honey-100), var(--honey-200));
  border-color: var(--color-border-strong);
}

.tray__initial {
  font-family: var(--font-display);
  font-size: 1.75rem;
  font-weight: 600;
  line-height: 1;
  color: var(--honey-600);
}

.tray--muted .tray__img {
  filter: grayscale(1) contrast(0.85);
  opacity: 0.6;
}

.tray--muted.tray--on-dark {
  background: var(--honey-800);
}

.tray--muted.tray--fallback {
  background: var(--honey-200);
}

.tray--muted.tray--fallback .tray__initial {
  color: var(--color-border-strong);
}
</style>
