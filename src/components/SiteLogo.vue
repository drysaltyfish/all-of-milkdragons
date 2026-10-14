<script setup>
/**
 * 校徽托盘。
 *
 * 三个数据事实决定了它的样子：
 *   1. 校徽中位宽高比 ≈ 3.7，绝大多数是「校名横排字标」——塞进方形缩略图会小到看不清，
 *      所以这里用整卡宽度的横条托盘。
 *   2. 六成以上的校徽是「白色 logo + 透明底」（站点导航栏上的白色版本），放浅底上等于
 *      隐形，所以给它们换一块深色暖棕托盘（.tray--on-dark）。托盘是站点自己的设计，
 *      不是校徽的一部分。
 *   3. 少数校徽**图片自己**带一整块实色底（白底/深蓝底/紫底），那才是要清掉的东西 ——
 *      由 process_logos.py 在数据阶段抠成透明，前端不需要为它们做兼容。
 *
 * 没有校徽（或加载失败）时退化成首字方块，保证每张卡片顶部重量一致。
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
/** 白色 logo：换深色托盘，否则在浅底上等于隐形 */
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
/* ★ 这里必须是 flex，不能是 grid。
   用 grid 时这是一个隐式的 auto 行，行高由图片自己撑出来，图片上的
   `max-height: 100%` 找不到确定的百分比参照，浏览器直接当 none ——
   图片会冲出托盘（实测 63px 高塞在 52px 里），每张卡片顶部的校徽高度就全乱了。
   flex 的交叉轴尺寸是确定的，能正常约束住。 */
.tray {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 3.25rem;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-sunken);
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

/* 没有校徽时的首字方块 */
.tray--fallback {
  background: linear-gradient(140deg, var(--honey-100), var(--honey-200));
  border-color: var(--color-border-strong);
}

.tray__initial {
  font-family: var(--font-display);
  font-size: 1.5rem;
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
  background: var(--color-surface-sunken);
}

.tray--muted.tray--fallback .tray__initial {
  color: var(--color-border-strong);
}
</style>
