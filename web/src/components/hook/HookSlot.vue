<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import { api, errorMessage } from '@/api/client'

import HookBlock from './HookBlock.vue'

const props = defineProps({
  slot: { type: String, required: true },
  context: { type: Object, default: () => ({}) },
  showTitle: { type: Boolean, default: false },
})

const blocks = ref([])
const loading = ref(false)

const contextParam = computed(() =>
  Object.keys(props.context || {}).length
    ? JSON.stringify(props.context)
    : undefined,
)

async function load() {
  loading.value = true
  try {
    const data = await api.get(`/hooks/slots/${props.slot}`, {
      query: { context: contextParam.value },
    })
    blocks.value = data?.blocks || []
  } catch (error) {
    //: 未登录或权限不足时插槽静默为空，不打扰用户。
    if (error?.status === 401 || error?.status === 403) {
      blocks.value = []
      return
    }
    ElMessage.error(errorMessage(error, '扩展加载失败'))
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(contextParam, load)

defineExpose({ refresh: load })
</script>

<template>
  <div v-if="blocks.length" class="hook-slot">
    <HookBlock
      v-for="block in blocks"
      :key="block.hook"
      :hook="block.hook"
      :title="block.title"
      :nodes="block.nodes"
      :context="context"
      :show-title="showTitle"
      :refresh="load"
    />
  </div>
</template>
