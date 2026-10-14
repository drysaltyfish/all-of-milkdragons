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
    <!-- 网友投稿的域名单独标出来：模板域名的「打不开」本身是有信息量的
         （域名注册了但停放着），投稿域名则只有真的跳到学校才有价值。
         标出来也让人一眼能判断哪些不是机器人扫出来的。 -->
    <span
      v-if="site.isCommunity"
      class="badge badge--community"
      title="这个域名是网友投稿的，不是自动扫描收录的"
    >
      网友投稿
    </span>
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
