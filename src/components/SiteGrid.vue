<script setup>
/**
 * 卡片墙。只负责排布，不碰数据内容。
 */
import SiteCard from './SiteCard.vue'

defineProps({
  sites: { type: Array, required: true },
  query: { type: String, default: '' },
})
</script>

<template>
  <ul class="grid">
    <li v-for="site in sites" :key="site.id" class="grid__cell">
      <SiteCard :site="site" :query="query" />
    </li>
  </ul>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--card-min), 1fr));
  gap: var(--space-4);
  padding: 0;
  margin: 0;
  list-style: none;
}

.grid__cell {
  display: flex;
}

.grid__cell > * {
  flex: 1 1 auto;
}

@media (max-width: 30rem) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
