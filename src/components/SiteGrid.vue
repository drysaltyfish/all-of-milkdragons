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
  /* ★ 这两处 min-width: 0 是必需的。
     `.card__foot` 是一行 flex-wrap: nowrap 的「落地链接 + 徽章」，它的
     min-content 宽度是两者 min-content 之和（实测 126px + 145px ≈ 279px）。
     而卡片默认 `min-width: auto`，会把这个 min-content 当成自己的最小宽度，
     于是轨道被压到最小（--card-min: 17.5rem）时，卡片比轨道宽出二三十像素，
     直接盖到右边那张卡片上 —— 实测 1280 / 1440 宽度下有 4 对卡片重叠、
     16 张卡片宽度不一致。把最小宽度交还给轨道，卡片就老实待在格子里了。 */
  min-width: 0;
}

.grid__cell > * {
  flex: 1 1 auto;
  min-width: 0;
}

@media (max-width: 30rem) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
