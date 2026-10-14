<script setup>
/**
 * 搜索高亮：把命中关键词的那一段包进 <mark>。
 * 完全用文本节点渲染（不用 v-html），所以不存在注入风险。
 */
import { computed } from 'vue'

const props = defineProps({
  text: { type: String, default: '' },
  query: { type: String, default: '' },
})

const segments = computed(() => {
  const text = props.text ?? ''
  const needle = props.query.trim().toLowerCase()
  if (!needle) return [{ text, hit: false }]

  const haystack = text.toLowerCase()
  const out = []
  let cursor = 0

  while (cursor < text.length) {
    const at = haystack.indexOf(needle, cursor)
    if (at === -1) {
      out.push({ text: text.slice(cursor), hit: false })
      break
    }
    if (at > cursor) out.push({ text: text.slice(cursor, at), hit: false })
    out.push({ text: text.slice(at, at + needle.length), hit: true })
    cursor = at + needle.length
  }

  return out.filter((segment) => segment.text)
})
</script>

<template>
  <span
    ><template v-for="(segment, index) in segments" :key="index"
      ><mark v-if="segment.hit">{{ segment.text }}</mark
      ><template v-else>{{ segment.text }}</template></template
    ></span
  >
</template>
