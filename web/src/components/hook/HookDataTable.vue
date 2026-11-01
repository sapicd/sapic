<script setup>
import { inject, onMounted, ref } from 'vue'

import { api, errorMessage } from '@/api/client'

const props = defineProps({
  node: { type: Object, required: true },
})

const runtime = inject('hookRuntime')

const columns = ref(props.node.columns || [])
const rows = ref([])
const total = ref(0)
const loading = ref(false)

async function load() {
  if (!props.node.source) return
  loading.value = true
  try {
    const data = await api.get(
      `/hooks/${runtime.hook}/data/${props.node.source}`,
      { query: { limit: props.node.page_size } },
    )
    rows.value = data?.items || []
    total.value = data?.total ?? rows.value.length
    if (!columns.value.length) {
      columns.value = data?.columns || []
    }
  } catch (error) {
    ElMessage.error(errorMessage(error, '数据加载失败'))
  } finally {
    loading.value = false
  }
}

async function onRowAction(action, row) {
  await runtime.runAction(action.action, {
    withForm: true,
    confirm: action.confirm,
    row,
  })
  await load()
}

onMounted(load)
</script>

<template>
  <el-table v-loading="loading" :data="rows" size="small" style="width: 100%">
    <el-table-column
      v-for="column in columns"
      :key="column.key"
      :prop="column.key"
      :label="column.label"
      :align="column.align || 'left'"
    />
    <el-table-column
      v-if="node.row_actions?.length"
      label="操作"
      width="140"
      align="right"
    >
      <template #default="{ row }">
        <el-button
          v-for="(action, index) in node.row_actions"
          :key="index"
          link
          :type="action.danger ? 'danger' : 'primary'"
          @click="onRowAction(action, row)"
        >
          {{ action.text }}
        </el-button>
      </template>
    </el-table-column>
    <template #empty>
      <el-empty :description="node.empty || '暂无数据'" :image-size="60" />
    </template>
  </el-table>
  <div v-if="total > rows.length" class="node-field__help">
    共 {{ total }} 条，当前显示 {{ rows.length }} 条
  </div>
</template>
