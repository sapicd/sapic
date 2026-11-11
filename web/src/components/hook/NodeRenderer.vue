<script setup>
import { computed, inject } from 'vue'

import HookDataTable from './HookDataTable.vue'
import NodeField from './NodeField.vue'
import { iconOf } from './icons'

const FIELD_TYPES = new Set([
  'input',
  'number',
  'password',
  'textarea',
  'switch',
  'select',
  'radio',
])

const BUTTON_TYPES = {
  default: '',
  primary: 'primary',
  success: 'success',
  warn: 'warning',
  danger: 'danger',
}
const TAG_TYPES = {
  info: 'info',
  notice: 'info',
  success: 'success',
  warn: 'warning',
  error: 'danger',
}
const ALERT_TYPES = {
  info: 'info',
  notice: 'info',
  success: 'success',
  warn: 'warning',
  error: 'error',
}
const SIZES = { small: 'small', normal: 'default', large: 'large' }

const props = defineProps({
  node: { type: Object, required: true },
})

const runtime = inject('hookRuntime')

const isField = computed(() => FIELD_TYPES.has(props.node.type))
const buttonType = computed(() => BUTTON_TYPES[props.node.variant] ?? '')
const tagType = computed(() => TAG_TYPES[props.node.level] ?? 'info')
const alertType = computed(() => ALERT_TYPES[props.node.level] ?? 'info')
const size = computed(() => SIZES[props.node.size])
const icon = computed(() => iconOf(props.node.icon))
const textClass = computed(() => ({
  'node-text': true,
  'is-muted': Boolean(props.node.muted),
}))

function px(value) {
  if (value === undefined || value === null || value === '') return undefined
  return typeof value === 'number' ? `${value}px` : value
}

async function onButton() {
  if (props.node.disabled) return
  if (props.node.action) {
    await runtime.runAction(props.node.action, {
      withForm: props.node.with_form,
      confirm: props.node.confirm,
    })
  } else if (props.node.refresh) {
    await runtime.refresh()
  }
}

async function onDropdownCommand(item) {
  if (!item?.action) return
  await runtime.runAction(item.action, {
    withForm: item.with_form,
    confirm: item.confirm,
  })
}

async function onRowAction(action) {
  await runtime.runAction(action.action, {
    withForm: true,
    confirm: action.confirm,
  })
}
</script>

<template>
  <!-- 容器 -->
  <fieldset v-if="node.type === 'fieldset'" class="node-fieldset">
    <legend v-if="node.legend || node.status">
      <span v-if="node.legend">{{ node.legend }}</span>
      <el-tag v-if="node.status" size="small" type="success" effect="plain">
        {{ node.status }}
      </el-tag>
    </legend>
    <NodeRenderer
      v-for="(child, index) in node.children"
      :key="child.id || index"
      :node="child"
    />
  </fieldset>

  <el-row v-else-if="node.type === 'row'" :gutter="node.gap || 12">
    <NodeRenderer
      v-for="(child, index) in node.children"
      :key="child.id || index"
      :node="child"
    />
  </el-row>

  <!-- 钩子面板声明的列宽在窄屏退化为整行，否则两列表单会被挤成半宽。 -->
  <el-col v-else-if="node.type === 'col'" :span="node.span || 12" :xs="24">
    <NodeRenderer
      v-for="(child, index) in node.children"
      :key="child.id || index"
      :node="child"
    />
  </el-col>

  <div v-else-if="node.type === 'group'" class="node-group">
    <div v-if="node.title" class="node-group__title">{{ node.title }}</div>
    <NodeRenderer
      v-for="(child, index) in node.children"
      :key="child.id || index"
      :node="child"
    />
  </div>

  <el-tabs v-else-if="node.type === 'tabs'">
    <el-tab-pane
      v-for="(child, index) in node.children"
      :key="child.id || index"
      :label="child.label || ''"
      :name="String(child.id || index)"
    >
      <NodeRenderer
        v-for="(grand, position) in child.children"
        :key="grand.id || position"
        :node="grand"
      />
    </el-tab-pane>
  </el-tabs>

  <el-collapse v-else-if="node.type === 'collapse'">
    <el-collapse-item
      v-for="(child, index) in node.children"
      :key="child.id || index"
      :title="child.title || ''"
      :name="String(child.id || index)"
    >
      <NodeRenderer
        v-for="(grand, position) in child.children"
        :key="grand.id || position"
        :node="grand"
      />
    </el-collapse-item>
  </el-collapse>

  <!-- 展示 -->
  <p v-else-if="node.type === 'text'" :class="textClass">{{ node.text }}</p>

  <el-alert
    v-else-if="node.type === 'alert'"
    class="node-alert"
    :type="alertType"
    :title="node.title || node.text"
    :description="node.title ? node.text : undefined"
    :closable="Boolean(node.closable)"
    show-icon
  />

  <div v-else-if="node.type === 'badge'" class="node-badge">
    <el-tag :type="tagType" size="small" :effect="node.dot ? 'plain' : 'light'">
      {{ node.text }}
    </el-tag>
  </div>

  <el-image
    v-else-if="node.type === 'image'"
    class="node-image"
    :src="node.src"
    :alt="node.alt || ''"
    :fit="node.fit || 'contain'"
    :style="{ width: px(node.width), height: px(node.height), maxWidth: '100%' }"
  />

  <pre v-else-if="node.type === 'code'" class="node-code"><code>{{ node.text }}</code></pre>

  <el-divider v-else-if="node.type === 'divider'">{{ node.label }}</el-divider>

  <HookDataTable v-else-if="node.type === 'table'" :node="node" />

  <div v-else-if="node.type === 'list'" class="node-list">
    <NodeRenderer
      v-for="(child, index) in node.children"
      :key="child.id || index"
      :node="child"
    />
    <el-empty
      v-if="!node.children?.length"
      :description="node.empty || '暂无内容'"
      :image-size="60"
    />
  </div>

  <div v-else-if="node.type === 'list_item'" class="node-list-item">
    <div class="node-list-item__body">
      <div class="node-list-item__title">{{ node.title }}</div>
      <div v-if="node.description" class="node-list-item__desc">
        {{ node.description }}
      </div>
    </div>
    <div class="node-list-item__actions">
      <el-button
        v-for="(action, index) in node.row_actions || []"
        :key="index"
        link
        :type="action.danger ? 'danger' : 'primary'"
        @click="onRowAction(action)"
      >
        {{ action.text }}
      </el-button>
    </div>
  </div>

  <!-- 输入 -->
  <NodeField v-else-if="isField" :node="node" />

  <!-- 交互 -->
  <el-button
    v-else-if="node.type === 'button' || node.type === 'dropdown_item'"
    class="node-button"
    :type="buttonType"
    :size="size"
    :icon="icon"
    :disabled="node.disabled"
    :title="node.disabled_reason"
    @click="onButton"
  >
    {{ node.text }}
  </el-button>

  <el-link
    v-else-if="node.type === 'link'"
    class="node-link"
    :type="node.variant && node.variant !== 'default' ? buttonType : 'primary'"
    :underline="false"
    :href="node.href"
    :target="node.target === 'blank' ? '_blank' : '_self'"
    rel="noopener noreferrer"
  >
    <el-icon v-if="icon"><component :is="icon" /></el-icon>
    {{ node.text }}
  </el-link>

  <el-dropdown v-else-if="node.type === 'dropdown'" @command="onDropdownCommand">
    <el-button :type="buttonType" :size="size" :icon="icon">
      {{ node.text }}
      <el-icon class="el-icon--right"><ArrowDown /></el-icon>
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="(child, index) in node.children"
          :key="index"
          :command="child"
          :disabled="child.disabled"
          :divided="child.danger"
        >
          {{ child.text }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>
