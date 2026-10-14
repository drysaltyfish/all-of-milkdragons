<script setup>
/**
 * 校徽。
 *
 * 三个数据事实决定了它的样子：
 *   1. 校徽中位宽高比 ≈ 3.7，绝大多数是「校名横排字标」——塞进方形缩略图会小到看不清，
 *      所以这里用整卡宽度的横条区。
 *   2. 六成以上的校徽是「白色 logo + 透明底」（站点导航栏上的白色版本）。
 *      它们放浅色卡片上等于隐形，但又不该给卡片塞一块深色底板，
 *      所以这里把这类 logo 整体压暗（见 .logo--on-light），让它在浅底上成立。
 *   3. 少数校徽自带一整块实色底（白底/深蓝底/紫底）。那些在 update 之后由
 *      process_logos.py 抠成透明，前端不再需要为它们做兼容。
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
/** 白色 logo：需要压暗才看得见 */
const needsDarkening = computed(() => !showFallback.value && Boolean(props.site.logoLight))
</script>

<template>
  <div class="logo" :class="{ 'logo--fallback': showFallback, 'logo--muted': site.status === 'offline' }">
    <img
      v-if="!showFallback"
      class="logo__img"
      :class="{ 'logo__img--on-light': needsDarkening }"
      :src="src"
      alt=""
      aria-hidden="true"
      loading="lazy"
      decoding="async"
      @error="failed = true"
    />
    <span v-else class="logo__initial" aria-hidden="true">{{ initial }}</span>
  </div>
</template>

<style scoped>
.logo {
  display: grid;
  place-items: center;
  width: 100%;
  height: 3.25rem;
}

.logo__img {
  width: auto;
  height: auto;
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

/* 白色 logo 放到浅色卡片上的适配：整体压暗成暖深色，
   保留原本的明暗层次，不做单色剪影。 */
.logo__img--on-light {
  filter: brightness(0.24) contrast(1.08) sepia(0.28);
}

/* 没有校徽时的首字方块 */
.logo--fallback .logo__initial {
  display: grid;
  place-items: center;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: var(--radius-md);
  background: linear-gradient(140deg, var(--honey-100), var(--honey-200));
  border: 1px solid var(--color-border-strong);
  font-family: var(--font-display);
  font-size: 1.5rem;
  font-weight: 600;
  line-height: 1;
  color: var(--honey-600);
}

.logo--muted .logo__img {
  filter: grayscale(1) contrast(0.85);
  opacity: 0.55;
}

.logo--muted .logo__img--on-light {
  filter: grayscale(1) brightness(0.5) contrast(0.9);
  opacity: 0.7;
}

.logo--muted.logo--fallback .logo__initial {
  background: var(--color-surface-sunken);
  color: var(--color-border-strong);
}
</style>
