<script setup>
import { computed, provide, reactive, watch } from 'vue'

import { api, errorMessage } from '@/api/client'
import { t } from '@/i18n'

import NodeRenderer from './NodeRenderer.vue'
import { hookText } from './text'

const props = defineProps({
  hook: { type: String, required: true },
  title: { type: String, default: '' },
  titleKey: { type: String, default: '' },
  nodes: { type: Array, default: () => [] },
  context: { type: Object, default: () => ({}) },
  showTitle: { type: Boolean, default: false },
  refresh: { type: Function, required: true },
})

//: 钩子只提供原始文案（多为中文）时照旧显示；带键或词表按模块名收录了译文才翻译。
const heading = computed(() =>
  hookText(props.hook, 'title', props.title, props.titleKey),
)

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
      await ElMessageBox.confirm(
        t('hooks.confirmText', { action }),
        t('hooks.confirmTitle'),
        { type: 'warning' },
      )
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
    ElMessage.error(errorMessage(error, t('hooks.actionFailed')))
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
      ElMessage.error(result.message || t('hooks.actionFailed'))
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
    <h4 v-if="showTitle && heading" class="hook-block__title">{{ heading }}</h4>
    <NodeRenderer
      v-for="(node, index) in nodes"
      :key="node.id || index"
      :node="node"
    />
  </section>
</template>
