<script setup>
import { provide, reactive, watch } from 'vue'

import { api, errorMessage } from '@/api/client'

import NodeRenderer from './NodeRenderer.vue'

const props = defineProps({
  hook: { type: String, required: true },
  title: { type: String, default: '' },
  nodes: { type: Array, default: () => [] },
  context: { type: Object, default: () => ({}) },
  showTitle: { type: Boolean, default: false },
  refresh: { type: Function, required: true },
})

const TOAST_TYPES = {
  success: 'success',
  error: 'error',
  warn: 'warning',
  info: 'info',
}

const values = reactive({})

function collectDefaults(nodes) {
  for (const node of nodes || []) {
    if (node.key && node.default !== undefined && values[node.key] === undefined) {
      values[node.key] = node.default
    }
    if (node.children) collectDefaults(node.children)
  }
}

collectDefaults(props.nodes)
watch(() => props.nodes, (nodes) => collectDefaults(nodes))

async function runAction(action, options = {}) {
  const { withForm = false, confirm = false, row = null } = options

  if (confirm) {
    try {
      await ElMessageBox.confirm(`确定执行「${action}」吗？`, '确认操作', {
        type: 'warning',
      })
    } catch (error) {
      return undefined
    }
  }

  let result
  try {
    result = await api.post(`/hooks/${props.hook}/actions/${action}`, {
      json: {
        values: withForm ? { ...values } : {},
        row,
        context: props.context,
      },
    })
  } catch (error) {
    ElMessage.error(errorMessage(error, '操作失败'))
    return undefined
  }
  if (!result) return undefined

  if (result.toast?.text) {
    ElMessage({
      type: TOAST_TYPES[result.toast.level] || 'info',
      message: result.toast.text,
    })
  }
  if (result.code !== 0) {
    if (!result.toast?.text) {
      ElMessage.error(result.message || '操作失败')
    }
    return result
  }
  if (result.refresh) {
    await props.refresh()
  }
  return result
}

provide('hookRuntime', {
  hook: props.hook,
  values,
  context: props.context,
  runAction,
  refresh: props.refresh,
})
</script>

<template>
  <section class="hook-block">
    <h4 v-if="showTitle && title" class="hook-block__title">{{ title }}</h4>
    <NodeRenderer
      v-for="(node, index) in nodes"
      :key="node.id || index"
      :node="node"
    />
  </section>
</template>
