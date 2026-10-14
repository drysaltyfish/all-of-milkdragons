<script setup>
/**
 * 页面装配层：只负责把「数据层」和「组件」接起来。
 * 所有筛选状态都住在这里，组件保持无状态 / 受控。
 */
import { computed, ref } from 'vue'
import AppHeader from './components/AppHeader.vue'
import SearchBar from './components/SearchBar.vue'
import FilterChips from './components/FilterChips.vue'
import SiteGrid from './components/SiteGrid.vue'
import EmptyState from './components/EmptyState.vue'
import ContributeDialog from './components/ContributeDialog.vue'
import { meta, sites, statusOptions, jumpOptions, contribute } from './data/index.js'
import { useSiteFilter } from './composables/useSiteFilter.js'

const query = ref('')
const status = ref('all')
const jump = ref('all')
const contributeOpen = ref(false)

const filters = { query, status, jump }
const { results, isFiltering, keyword } = useSiteFilter(sites, filters)

const matched = computed(() => results.value.length)

const statusFilters = statusOptions.map((option) =>
  option.value === 'all' ? { ...option, label: '不限状态' } : option,
)
const jumpFilters = jumpOptions.map((option) =>
  option.value === 'all' ? { ...option, label: '不限跳转' } : option,
)

function resetAll() {
  query.value = ''
  status.value = 'all'
  jump.value = 'all'
}
</script>

<template>
  <a class="skip-link" href="#site-list">跳到域名列表</a>

  <div class="shell">
    <AppHeader
      :total="meta.total"
      :online="meta.online"
      :offline="meta.offline"
      :with-logo="meta.withLogo"
      :generated-at="meta.generatedAt"
      :contribute-label="contribute.buttonLabel"
      :contribute-hint="contribute.hint"
      @contribute="contributeOpen = true"
    />

    <section class="panel" aria-labelledby="panel-title">
      <h2 id="panel-title" class="visually-hidden">搜索与筛选</h2>
      <SearchBar v-model="query" :matched="matched" :total="meta.total" />
      <div class="panel__filters">
        <FilterChips v-model="status" legend="状态" :options="statusFilters" />
        <FilterChips v-model="jump" legend="跳转" :options="jumpFilters" />
        <button v-if="isFiltering" type="button" class="panel__reset" @click="resetAll">
          重置
        </button>
      </div>
    </section>

    <main id="site-list">
      <SiteGrid v-if="matched" :sites="results" :query="keyword" />
      <EmptyState v-else :query="query" @reset="resetAll" />
    </main>

    <footer class="foot">
      <p>
        数据来自 <code>result.json</code>（DNS 探测 + HTTP 跳转追踪 + 标题/校徽抓取），
        由 <code>scripts/build-data.mjs</code> 生成 <code>src/data/sites.json</code>。
      </p>
      <p class="foot__note">
        「可访问」只代表抓取当时回到了 2xx/3xx，站点状态随时会变；打不开的域名同样保留在墙上。
      </p>
      <p class="foot__note">
        列表里没有你想找的域名？
        <button type="button" class="foot__link" @click="contributeOpen = true">
          点这里投稿
        </button>
        —— 可以看看它能收录什么样的域名、以及怎么投。
      </p>
    </footer>
  </div>

  <ContributeDialog v-model:open="contributeOpen" :content="contribute" />
</template>

<style scoped>
.shell {
  width: 100%;
  max-width: var(--shell-max);
  margin: 0 auto;
  padding: 0 var(--shell-pad) var(--space-8);
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.panel {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: color-mix(in srgb, var(--color-bg) 88%, transparent);
  backdrop-filter: blur(12px);
  box-shadow: var(--shadow-sm);
}

@supports not (backdrop-filter: blur(4px)) {
  .panel {
    background: var(--color-bg);
  }
}

.panel__filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3) var(--space-5);
}

.panel__reset {
  min-height: 2.375rem;
  padding: var(--space-1) var(--space-4);
  border: 1px dashed var(--color-border-strong);
  border-radius: var(--radius-pill);
  background: transparent;
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--color-primary-text);
  transition: background var(--dur-fast) var(--ease-out);
}

.panel__reset:hover {
  background: var(--color-primary-soft);
}

.foot {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-top: var(--space-5);
  border-top: 1px solid var(--color-border);
  font-size: var(--text-sm);
  color: var(--color-text-soft);
}

.foot code {
  padding: 0 0.25em;
  border-radius: var(--radius-sm);
  background: var(--color-surface-sunken);
  font-family: var(--font-mono);
  font-size: 0.9em;
  color: var(--color-primary-text);
}

.foot__note {
  opacity: 0.9;
}

/* 页脚里的投稿入口：做成行内链接的样子，但语义上是 button
   （它打开的是弹窗，不是导航，用 <a> 会骗读屏和「在新标签打开」的期待） */
.foot__link {
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  font-weight: 700;
  color: var(--color-primary-text);
  text-decoration: underline;
  text-underline-offset: 0.2em;
}

.foot__link:hover {
  color: var(--color-primary-strong);
}

@media (max-width: 40rem) {
  .panel {
    position: static;
  }
}
</style>
