<script setup>
/**
 * 页头：站名 + 一句话说明 + 投稿入口 + 四个统计数字。
 * 纯展示组件，所有内容通过 props 传入，点击只 emit 事件。
 */
defineProps({
  total: { type: Number, required: true },
  online: { type: Number, required: true },
  offline: { type: Number, required: true },
  withLogo: { type: Number, required: true },
  generatedAt: { type: String, default: '' },
  contributeLabel: { type: String, default: '' },
  contributeHint: { type: String, default: '' },
})

const emit = defineEmits(['contribute'])
</script>

<template>
  <header class="hero">
    <div class="hero__brand">
      <span class="hero__mark" aria-hidden="true">奶</span>
      <div>
        <p class="hero__eyebrow">All of Milkdragons</p>
        <h1 class="hero__title">奶龙大学导航</h1>
      </div>
    </div>

    <p class="hero__lede">
      全网「奶龙大学 / 奶蛙大学」系列仿冒域名的卡片墙。点卡片去看域名本身，
      点右下角的小链接直接去它最终落地的站点。
    </p>

    <!-- 投稿入口。放在首屏第一屏里，因为「列表里没有我想找的域名」是这个页面
         最主要的未满足需求，藏到页脚等于没有。 -->
    <div v-if="contributeLabel" class="hero__actions">
      <button type="button" class="hero__cta" @click="emit('contribute')">
        {{ contributeLabel }}
      </button>
      <p v-if="contributeHint" class="hero__hint">{{ contributeHint }}</p>
    </div>

    <dl class="stats">
      <div class="stats__item">
        <dt>收录域名</dt>
        <dd>{{ total }}</dd>
      </div>
      <div class="stats__item stats__item--ok">
        <dt>可访问</dt>
        <dd>{{ online }}</dd>
      </div>
      <div class="stats__item stats__item--bad">
        <dt>打不开</dt>
        <dd>{{ offline }}</dd>
      </div>
      <div class="stats__item">
        <dt>抓到校徽</dt>
        <dd>{{ withLogo }}</dd>
      </div>
    </dl>

    <p v-if="generatedAt" class="hero__stamp">数据抓取于 {{ generatedAt }}</p>
  </header>
</template>

<style scoped>
.hero {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding-top: var(--space-7);
}

.hero__brand {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.hero__mark {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  width: 3.5rem;
  height: 3.5rem;
  border-radius: var(--radius-lg);
  background: linear-gradient(140deg, var(--honey-400), var(--honey-600));
  box-shadow: var(--shadow-md);
  font-family: var(--font-display);
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--color-text-on-primary);
  rotate: -4deg;
}

.hero__eyebrow {
  font-family: var(--font-display);
  font-size: var(--text-xs);
  font-weight: 500;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--color-primary-strong);
}

.hero__title {
  font-size: var(--text-3xl);
}

.hero__lede {
  max-width: 44rem;
  font-size: var(--text-lg);
  color: var(--color-text-soft);
}

.hero__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2) var(--space-4);
}

.hero__cta {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  min-height: 2.75rem;
  padding: 0 var(--space-5);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-pill);
  background: var(--color-surface);
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--color-primary-text);
  box-shadow: var(--shadow-xs);
  transition:
    background var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out);
}

.hero__cta:hover {
  background: var(--color-primary-soft);
  border-color: var(--color-primary);
}

.hero__hint {
  flex: 1 1 16rem;
  min-width: 0;
  max-width: 38rem;
  font-size: var(--text-sm);
  color: var(--color-text-soft);
}

.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr));
  gap: var(--space-3);
}

.stats__item {
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  box-shadow: var(--shadow-xs);
}

.stats__item dt {
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--color-text-soft);
  text-transform: uppercase;
}

.stats__item dd {
  margin-top: var(--space-1);
  font-family: var(--font-display);
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--color-text-strong);
  font-variant-numeric: tabular-nums;
}

.stats__item--ok dd {
  color: var(--color-success);
}

.stats__item--bad dd {
  color: var(--color-danger);
}

.hero__stamp {
  font-size: var(--text-sm);
  color: var(--color-text-soft);
}
</style>
