<script setup>
/**
 * 空结果提示：给出「怎么调回去」的出口，而不是干巴巴一句没有结果。
 */
defineProps({
  query: { type: String, default: '' },
})

defineEmits(['reset'])
</script>

<template>
  <div class="empty">
    <svg class="empty__art" viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <circle cx="27" cy="27" r="16" fill="none" stroke="currentColor" stroke-width="4" />
      <path d="M39 39 53 53" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" />
      <path d="M20 27h14" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" />
    </svg>
    <h2 class="empty__title">没有匹配的域名</h2>
    <p class="empty__body">
      <template v-if="query">关键词「{{ query }}」没搜到任何奶龙大学，</template>
      <template v-else>当前筛选条件下没有任何奶龙大学，</template>
      试试缩短关键词，或者换个跳转/状态筛选。
    </p>
    <button type="button" class="empty__reset" @click="$emit('reset')">清空搜索与筛选</button>
  </div>
</template>

<style scoped>
.empty {
  display: grid;
  justify-items: center;
  gap: var(--space-3);
  padding: var(--space-8) var(--space-4);
  border: 1px dashed var(--color-border-strong);
  border-radius: var(--radius-xl);
  background: var(--color-surface);
  text-align: center;
}

.empty__art {
  width: 4rem;
  height: 4rem;
  color: var(--honey-400);
}

.empty__title {
  font-size: var(--text-xl);
}

.empty__body {
  max-width: 32rem;
  color: var(--color-text-soft);
}

.empty__reset {
  min-height: 2.75rem;
  padding: var(--space-2) var(--space-5);
  border: 1px solid var(--color-primary-strong);
  border-radius: var(--radius-pill);
  background: var(--color-primary);
  font-weight: 700;
  color: var(--color-text-on-primary);
  transition: filter var(--dur-fast) var(--ease-out);
}

.empty__reset:hover {
  filter: brightness(1.06);
}
</style>
