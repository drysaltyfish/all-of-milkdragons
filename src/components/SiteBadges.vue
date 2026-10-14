<script setup>
/**
 * 卡片上的两枚徽章：跳转类型 + 可访问状态。
 * 状态徽章只对「打不开」的卡片显示具体原因（403/超时…），
 * 能打开的卡片不啰嗦，只留一个绿色的「可访问」。
 */
import { computed } from 'vue'
import { jumpTypeLabels, jumpTypeDescriptions } from '../data/index.js'

const props = defineProps({
  site: { type: Object, required: true },
})

const jumpLabel = computed(() => jumpTypeLabels[props.site.jumpType] || '未知')
const jumpHint = computed(() => jumpTypeDescriptions[props.site.jumpType] || '')
</script>

<template>
  <div class="badges">
    <span class="badge badge--jump" :title="`跳转方式：${jumpHint}`">
      {{ jumpLabel }}
    </span>
    <span
      class="badge"
      :class="site.status === 'online' ? 'badge--online' : 'badge--offline'"
      :title="site.statusDetail || site.statusLabel"
    >
      {{ site.statusLabel }}
    </span>
  </div>
</template>

<style scoped>
.badges {
  display: flex;
  flex: 0 0 auto;
  gap: var(--space-1);
}
</style>
