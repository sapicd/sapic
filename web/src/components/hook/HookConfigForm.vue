<script setup>
import { computed, provide, reactive, watch } from 'vue'

import { t } from '@/i18n'

import NodeRenderer from './NodeRenderer.vue'
import { hookText } from './text'

const props = defineProps({
  config: { type: Object, required: true },
  saving: { type: Boolean, default: false },
  pinging: { type: Boolean, default: false },
})

const emit = defineEmits(['save', 'ping'])

const form = reactive({})

function reset(values) {
  const source = values || {}
  props.config.fields.forEach((field) => {
    const value = source[field.key]
    if (value !== undefined && value !== null) {
      form[field.key] = value
      return
    }
    //: 没保存过的字段回落到 schema 默认值，switch 才不会假装是关闭状态。
    form[field.key] = field.default ?? ''
  })
}

watch(() => props.config.values, reset, { immediate: true, deep: true })

//: 借用节点词表渲染表单，字段控件与插槽完全一致；动作交回页面处理。
provide('hookRuntime', {
  hook: props.config.name,
  values: form,
  context: {},
  runAction: () => undefined,
  refresh: () => undefined,
})

const canPing = computed(() =>
  (props.config.actions || []).some((action) => action.name === 'ping'),
)

//: manifest 文案优先用钩子声明的键，其次按模块名兜底，最后才是钩子原文。
function localized(field) {
  return hookText(
    props.config.name,
    field,
    props.config[field],
    props.config[`${field}_key`],
  )
}
</script>

<template>
  <section class="hook-config">
    <header class="hook-config__header">
      <div class="hook-config__title">
        <span>{{ localized('title') }}</span>
        <el-tag v-if="config.version" size="small" type="info" effect="plain">
          v{{ config.version }}
        </el-tag>
      </div>
      <div class="form-actions">
        <el-button
          v-if="canPing"
          size="small"
          :loading="pinging"
          @click="emit('ping', { ...form })"
        >
          {{ t('hooks.check') }}
        </el-button>
        <el-button
          type="primary"
          size="small"
          :loading="saving"
          @click="emit('save', { ...form })"
        >
          {{ t('common.save') }}
        </el-button>
      </div>
    </header>

    <p v-if="config.description" class="hook-config__desc">
      {{ localized('description') }}
    </p>

    <NodeRenderer v-for="field in config.fields" :key="field.key" :node="field" />
  </section>
</template>
