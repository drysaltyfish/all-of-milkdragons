<script setup>
/**
 * 一排筛选 chip（单选）。用 aria-pressed 表达选中态，而不是只靠颜色。
 */
defineProps({
  options: { type: Array, required: true },
  modelValue: { type: String, required: true },
  legend: { type: String, required: true },
})

defineEmits(['update:modelValue'])
</script>

<template>
  <div class="filters" role="group" :aria-label="legend">
    <span class="filters__legend" aria-hidden="true">{{ legend }}</span>
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      class="chip"
      :class="{ 'chip--active': option.value === modelValue }"
      :aria-pressed="option.value === modelValue"
      :title="option.description || ''"
      @click="$emit('update:modelValue', option.value)"
    >
      {{ option.label }}
      <span class="chip__count">{{ option.count }}</span>
    </button>
  </div>
</template>

<style scoped>
.filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.filters__legend {
  margin-right: var(--space-1);
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--color-text-soft);
  text-transform: uppercase;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  /* 44px 触控高度（含 padding） */
  min-height: 2.375rem;
  padding: var(--space-1) var(--space-3);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-pill);
  background: var(--color-surface-raised);
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--color-text);
  transition:
    background var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out),
    color var(--dur-fast) var(--ease-out);
}

.chip:hover {
  background: var(--color-primary-soft);
  border-color: var(--color-primary);
}

.chip--active {
  background: var(--color-primary);
  border-color: var(--color-primary-strong);
  color: var(--color-text-on-primary);
}

.chip__count {
  font-variant-numeric: tabular-nums;
  font-size: var(--text-xs);
  opacity: 0.75;
}
</style>
