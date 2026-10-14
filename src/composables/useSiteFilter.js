import { computed } from 'vue'

/**
 * 搜索 + 筛选逻辑，独立于任何组件。
 *
 * @param {Array} source 数据层给的全量站点
 * @param {{ query: import('vue').Ref<string>, status: import('vue').Ref<string>, jump: import('vue').Ref<string> }} filters
 * @returns {{ results: import('vue').ComputedRef<Array>, isFiltering: import('vue').ComputedRef<boolean>, keyword: import('vue').ComputedRef<string> }}
 */
export function useSiteFilter(source, filters) {
  const keyword = computed(() => filters.query.value.trim().toLowerCase())

  const results = computed(() => {
    const q = keyword.value
    const status = filters.status.value
    const jump = filters.jump.value

    return source.filter((site) => {
      if (status !== 'all' && site.status !== status) return false
      if (jump !== 'all' && site.jumpType !== jump) return false
      if (!q) return true
      return site.searchText.includes(q)
    })
  })

  const isFiltering = computed(
    () => Boolean(keyword.value) || filters.status.value !== 'all' || filters.jump.value !== 'all',
  )

  return { results, isFiltering, keyword }
}
