<script setup>
/**
 * 「投稿没收录的域名」弹窗。
 *
 * 用原生 <dialog> + showModal()，白嫖三件事：焦点陷阱、Esc 关闭、
 * 背景 inert（读屏和 Tab 都出不去）。自己用 div 糊一个 modal 这三样都得手写，
 * 而且很容易写漏。
 *
 * 文案全部来自 data 层的 contribute 对象，组件不认识任何一句话。
 */
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  content: { type: Object, required: true },
})

const emit = defineEmits(['update:open'])

const dlg = ref(null)

watch(
  () => props.open,
  async (isOpen) => {
    await nextTick()
    const el = dlg.value
    if (!el) return
    if (isOpen && !el.open) el.showModal()
    else if (!isOpen && el.open) el.close()
  },
)

/** 关闭：只改状态，由上面的 watch 负责真正调用 close()，避免两处各关一次 */
function close() {
  emit('update:open', false)
}

/** 点遮罩关闭。遮罩的点击事件 target 就是 <dialog> 本身。 */
function onBackdropClick(event) {
  if (event.target === dlg.value) close()
}
</script>

<template>
  <dialog
    ref="dlg"
    class="dlg"
    aria-labelledby="contribute-title"
    @close="close"
    @click="onBackdropClick"
  >
    <div class="dlg__body">
      <header class="dlg__head">
        <h2 id="contribute-title" class="dlg__title">{{ content.title }}</h2>
        <button type="button" class="dlg__close" aria-label="关闭" @click="close">
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
            <path
              d="M4 4l8 8M12 4l-8 8"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
            />
          </svg>
        </button>
      </header>

      <p v-for="(line, i) in content.intro" :key="`intro-${i}`" class="dlg__intro">
        {{ line }}
      </p>

      <section class="dlg__section">
        <h3 class="dlg__h3">{{ content.requirementsTitle }}</h3>
        <ul class="dlg__list">
          <li v-for="item in content.requirements" :key="item.title" class="dlg__item">
            <span class="dlg__dot dlg__dot--req" aria-hidden="true"></span>
            <div>
              <p class="dlg__item-title">{{ item.title }}</p>
              <p class="dlg__item-detail">{{ item.detail }}</p>
            </div>
          </li>
        </ul>
      </section>

      <section class="dlg__section">
        <h3 class="dlg__h3">{{ content.stepsTitle }}</h3>
        <ol class="dlg__list dlg__list--steps">
          <li v-for="(item, i) in content.steps" :key="item.title" class="dlg__item">
            <span class="dlg__step" aria-hidden="true">{{ i + 1 }}</span>
            <div>
              <p class="dlg__item-title">{{ item.title }}</p>
              <p class="dlg__item-detail">{{ item.detail }}</p>
            </div>
          </li>
        </ol>
      </section>

      <section class="dlg__section">
        <h3 class="dlg__h3">{{ content.outcomesTitle }}</h3>
        <ul class="dlg__list">
          <li
            v-for="item in content.outcomes"
            :key="item.title"
            class="dlg__item dlg__item--outcome"
            :class="`dlg__item--${item.kind}`"
          >
            <span class="dlg__dot" aria-hidden="true"></span>
            <div>
              <p class="dlg__item-title">{{ item.title }}</p>
              <p class="dlg__item-detail">{{ item.detail }}</p>
            </div>
          </li>
        </ul>
      </section>

      <section class="dlg__section dlg__section--notes">
        <p v-for="(note, i) in content.notes" :key="`note-${i}`" class="dlg__note">
          {{ note }}
        </p>
      </section>

      <div class="dlg__cta">
        <a
          class="dlg__button"
          :href="content.formUrl"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ content.ctaLabel }}
          <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
            <path
              d="M6 3.5h6.5V10M12.5 3.5 4 12"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </a>
        <p class="dlg__cta-note">{{ content.ctaNote }}</p>
      </div>
    </div>
  </dialog>
</template>

<style scoped>
.dlg {
  /* ★ margin: auto 是必需的，不是可选的居中写法。
     浏览器 UA 样式表靠 `dialog { margin: auto }` + left/right:0 把模态框居中，
     而 base.css 里有一条全局 `* { margin: 0 }` 重置 —— 它把这条也一起清掉了，
     结果弹窗会死死贴在左上角（实测 getBoundingClientRect 是 left:0 top:0）。
     自己写回来。 */
  margin: auto;
  width: min(46rem, calc(100vw - 2rem));
  max-height: min(84vh, 46rem);
  padding: 0;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-xl);
  background: var(--color-surface);
  box-shadow: var(--shadow-lg);
  color: var(--color-text);
  overflow: hidden;
}

.dlg::backdrop {
  background: rgb(40 28 18 / 45%);
  backdrop-filter: blur(2px);
}

.dlg__body {
  max-height: inherit;
  overflow-y: auto;
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  overscroll-behavior: contain;
}

.dlg__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.dlg__title {
  font-size: var(--text-2xl);
}

.dlg__close {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  width: 2.25rem;
  height: 2.25rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-surface-sunken);
  color: var(--color-text-soft);
  transition:
    background var(--dur-fast) var(--ease-out),
    color var(--dur-fast) var(--ease-out);
}

.dlg__close:hover {
  background: var(--color-primary-soft);
  color: var(--color-primary-text);
}

.dlg__intro {
  max-width: 40rem;
  color: var(--color-text-soft);
}

.dlg__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-border);
}

.dlg__section--notes {
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-soft);
}

.dlg__h3 {
  font-size: var(--text-lg);
}

.dlg__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}

.dlg__item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
}

.dlg__item-title {
  font-weight: 700;
  color: var(--color-text-strong);
}

.dlg__item-detail {
  margin-top: 0.15rem;
  font-size: var(--text-sm);
  color: var(--color-text-soft);
}

/* 要求列表的圆点 */
.dlg__dot {
  flex: 0 0 auto;
  width: 0.5rem;
  height: 0.5rem;
  margin-top: 0.55rem;
  border-radius: var(--radius-pill);
  background: var(--color-border-strong);
}

/* 三种结局各自配色，和卡片上的徽章语义保持一致 */
.dlg__item--ok .dlg__dot {
  background: var(--color-success);
}

.dlg__item--wait .dlg__dot {
  background: var(--honey-500);
}

.dlg__item--bad .dlg__dot {
  background: var(--color-danger);
}

/* 步骤用序号方块，比圆点更能表达「先后顺序」 */
.dlg__list--steps {
  counter-reset: step;
}

.dlg__step {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: var(--radius-sm);
  background: var(--color-primary-soft);
  border: 1px solid var(--color-border-strong);
  font-family: var(--font-display);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-primary-text);
}

.dlg__note {
  padding-left: var(--space-4);
  position: relative;
}

.dlg__note::before {
  content: '·';
  position: absolute;
  left: var(--space-2);
  color: var(--color-primary-strong);
  font-weight: 700;
}

.dlg__cta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2) var(--space-4);
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-border);
}

.dlg__button {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 2.75rem;
  padding: 0 var(--space-5);
  border-radius: var(--radius-pill);
  background: var(--color-primary);
  color: var(--color-text-on-primary);
  font-weight: 700;
  text-decoration: none;
  box-shadow: var(--shadow-sm);
  transition:
    background var(--dur-fast) var(--ease-out),
    transform var(--dur-fast) var(--ease-out);
}

.dlg__button:hover {
  background: var(--color-primary-strong);
  text-decoration: none;
}

.dlg__button:active {
  transform: translateY(1px);
}

.dlg__cta-note {
  font-size: var(--text-sm);
  color: var(--color-text-soft);
}

@media (max-width: 30rem) {
  .dlg {
    width: calc(100vw - 1rem);
    max-height: 92vh;
  }

  .dlg__body {
    padding: var(--space-4);
  }
}

@media (prefers-reduced-motion: reduce) {
  .dlg__button:active {
    transform: none;
  }
}
</style>
