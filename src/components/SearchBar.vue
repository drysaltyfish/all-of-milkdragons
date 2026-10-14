<script setup>
/**
 * 搜索框。支持「/」快捷聚焦、Esc 清空，并且是受控组件。
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps({
  modelValue: { type: String, default: '' },
  matched: { type: Number, required: true },
  total: { type: Number, required: true },
})

const emit = defineEmits(['update:modelValue'])

const inputRef = ref(null)

function onInput(event) {
  emit('update:modelValue', event.target.value)
}

function clear() {
  emit('update:modelValue', '')
  inputRef.value?.focus()
}

function onKeydown(event) {
  if (event.key === '/' && document.activeElement !== inputRef.value) {
    const tag = document.activeElement?.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA') return
    event.preventDefault()
    inputRef.value?.focus()
    return
  }
  if (event.key === 'Escape' && document.activeElement === inputRef.value) {
    clear()
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="search">
    <div class="search__field">
      <svg class="search__icon" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
        <circle cx="9" cy="9" r="5.75" fill="none" stroke="currentColor" stroke-width="2" />
        <path d="M13.4 13.4 17.5 17.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
      </svg>

      <label class="visually-hidden" for="site-search">按网址或学校名称搜索</label>
      <input
        id="site-search"
        ref="inputRef"
        class="search__input"
        type="search"
        name="site-search"
        autocomplete="off"
        spellcheck="false"
        placeholder="搜网址或学校名，例如 bit.edu.cn / 北京理工 / 奶龙"
        :value="modelValue"
        @input="onInput"
      />

      <button v-if="modelValue" type="button" class="search__clear" @click="clear">
        <span class="visually-hidden">清空搜索</span>
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
          <path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>
      </button>
    </div>

    <p class="search__count" role="status" aria-live="polite">
      <span>命中 <strong>{{ matched }}</strong> / {{ total }} 个域名</span>
      <span class="search__hint">按 <kbd class="search__kbd">/</kbd> 聚焦搜索</span>
    </p>
  </div>
</template>

<style scoped>
.search {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.search__field {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3) var(--space-2) var(--space-4);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-pill);
  background: var(--color-surface-raised);
  box-shadow: var(--shadow-sm);
  transition:
    border-color var(--dur-fast) var(--ease-out),
    box-shadow var(--dur-fast) var(--ease-out);
}

.search__field:focus-within {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-md), 0 0 0 4px rgba(233, 169, 58, 0.28);
}

.search__icon {
  flex: 0 0 auto;
  width: 1.125rem;
  height: 1.125rem;
  color: var(--color-primary-strong);
}

.search__input {
  flex: 1 1 auto;
  min-width: 0;
  padding: var(--space-2) 0;
  border: 0;
  background: none;
  font-size: var(--text-lg);
}

.search__input::placeholder {
  color: var(--color-text-soft);
  opacity: 0.85;
}

.search__input:focus-visible {
  outline: none;
}

/* 去掉 Chrome/Safari 自带的清除按钮，用自己的那一个 */
.search__input::-webkit-search-cancel-button {
  display: none;
}

.search__clear {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  width: 2rem;
  height: 2rem;
  border: 0;
  border-radius: var(--radius-pill);
  background: var(--color-primary-soft);
  color: var(--color-primary-strong);
  transition: background var(--dur-fast) var(--ease-out);
}

.search__clear:hover {
  background: var(--honey-300);
}

.search__count {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
  padding: 0 var(--space-4);
  font-size: var(--text-sm);
  color: var(--color-text-soft);
}

.search__hint {
  flex: 0 0 auto;
  font-size: var(--text-xs);
}

.search__count strong {
  color: var(--color-text-strong);
  font-variant-numeric: tabular-nums;
}

.search__kbd {
  display: inline-block;
  min-width: 1.35rem;
  padding: 0 0.3rem;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  background: var(--color-surface-raised);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  text-align: center;
  color: var(--color-text-soft);
}
</style>
