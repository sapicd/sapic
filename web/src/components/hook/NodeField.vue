<script setup>
import { computed, inject, onMounted, ref } from 'vue'

import { api } from '@/api/client'

const props = defineProps({
  node: { type: Object, required: true },
})

const runtime = inject('hookRuntime')
const options = ref(props.node.options || [])

const value = computed({
  get: () => runtime.values[props.node.key],
  set: (next) => {
    runtime.values[props.node.key] = next
  },
})

onMounted(async () => {
  if (props.node.type !== 'select' || !props.node.source) return
  if (options.value.length) return
  try {
    const data = await api.get(`/hooks/${runtime.hook}/data/${props.node.source}`)
    options.value = (data?.items || []).map((item) => ({
      label: item.label ?? item.name ?? item.value,
      value: item.value ?? item.name,
    }))
  } catch (error) {
    options.value = []
  }
})
</script>

<template>
  <div class="node-field">
    <label class="node-field__label" :class="{ 'is-required': node.required }">
      {{ node.label || node.key }}
    </label>
    <div class="node-field__control">
      <el-input
        v-if="node.type === 'input'"
        v-model="value"
        :placeholder="node.placeholder"
        :readonly="node.readonly"
        :disabled="node.disabled"
        :maxlength="node.maxlength"
        clearable
      >
        <template v-if="node.prefix" #prefix>{{ node.prefix }}</template>
        <template v-if="node.suffix" #suffix>{{ node.suffix }}</template>
      </el-input>

      <el-input
        v-else-if="node.type === 'password'"
        v-model="value"
        type="password"
        :placeholder="node.placeholder"
        :disabled="node.disabled"
        :show-password="node.reveal !== false"
      />

      <el-input
        v-else-if="node.type === 'textarea'"
        v-model="value"
        type="textarea"
        :rows="node.rows || 3"
        :placeholder="node.placeholder"
        :disabled="node.disabled"
        :maxlength="node.maxlength"
        :class="{ 'is-mono': node.mono }"
      />

      <el-input-number
        v-else-if="node.type === 'number'"
        v-model="value"
        :min="node.min"
        :max="node.max"
        :step="node.step || 1"
        :disabled="node.disabled"
        controls-position="right"
        style="width: 100%"
      />

      <el-switch
        v-else-if="node.type === 'switch'"
        v-model="value"
        :disabled="node.disabled"
        :active-text="node.active_text"
        :inactive-text="node.inactive_text"
      />

      <el-select
        v-else-if="node.type === 'select'"
        v-model="value"
        :placeholder="node.placeholder"
        :disabled="node.disabled"
        :multiple="node.multiple"
        clearable
        style="width: 100%"
      >
        <el-option
          v-for="(option, index) in options"
          :key="index"
          :label="option.label"
          :value="option.value"
          :disabled="option.disabled"
        />
      </el-select>

      <el-radio-group
        v-else-if="node.type === 'radio'"
        v-model="value"
        :disabled="node.disabled"
      >
        <el-radio
          v-for="(option, index) in options"
          :key="index"
          :value="option.value"
        >
          {{ option.label }}
        </el-radio>
      </el-radio-group>

      <div v-if="node.help" class="node-field__help">{{ node.help }}</div>
    </div>
  </div>
</template>
