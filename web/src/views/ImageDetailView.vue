<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, errorMessage } from '@/api/client'
import HookSlot from '@/components/hook/HookSlot.vue'
import { useSessionStore } from '@/stores/session'
import { absoluteUrl, formatSize, formatTime } from '@/utils/format'

const VISIBILITIES = [
  { label: '跟随相册', value: '' },
  { label: '公开', value: 'public' },
  { label: '私有', value: 'private' },
  { label: '共享', value: 'shared' },
]

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const image = ref(null)
const replicas = ref([])
const loading = ref(false)
const saving = ref(false)
const form = reactive({ title: '', visibility: '' })

async function load() {
  loading.value = true
  try {
    const data = await api.get(`/images/${route.params.sha}`)
    image.value = data?.image || null
    replicas.value = image.value?.replicas || []
    form.title = image.value?.title || ''
    //: 空串表示没有单图覆盖，可见性跟随相册。
    form.visibility = image.value?.visibility || ''
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载图片失败'))
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const data = await api.patch(`/images/${route.params.sha}`, {
      json: { title: form.title, visibility: form.visibility || null },
    })
    if (data?.image) image.value = { ...image.value, ...data.image }
    ElMessage.success('已保存')
  } catch (error) {
    ElMessage.error(errorMessage(error, '保存失败'))
  } finally {
    saving.value = false
  }
}

async function remove() {
  try {
    await ElMessageBox.confirm('删除后不可恢复，确定继续吗？', '删除图片', {
      type: 'warning',
    })
  } catch (error) {
    return
  }
  try {
    await api.del(`/images/${route.params.sha}`)
    ElMessage.success('已删除')
    router.push({ name: 'images' })
  } catch (error) {
    ElMessage.error(errorMessage(error, '删除失败'))
  }
}

async function copy() {
  try {
    await navigator.clipboard.writeText(absoluteUrl(image.value?.src))
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    ElMessage.warning('复制失败，请手动复制')
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="page">
    <div class="page__header">
      <h2 class="page__title">{{ image?.filename || '图片详情' }}</h2>
      <el-button @click="router.push({ name: 'images' })">返回列表</el-button>
    </div>

    <el-row v-if="image" :gutter="16">
      <el-col :xs="24" :md="14">
        <el-card>
          <div class="detail-preview">
            <el-image
              :src="image.src"
              fit="contain"
              :preview-src-list="[absoluteUrl(image.src)]"
              preview-teleported
            />
          </div>
          <div class="detail-meta">
            <el-tag effect="plain">{{ image.mime || '未知类型' }}</el-tag>
            <el-tag effect="plain">{{ formatSize(image.size) }}</el-tag>
            <el-tag effect="plain">{{ formatTime(image.created_at) }}</el-tag>
            <el-tag effect="plain">{{ image.visibility || '跟随相册' }}</el-tag>
            <el-button size="small" type="primary" plain @click="copy">
              复制链接
            </el-button>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="10">
        <el-card v-if="session.authenticated">
          <template #header>编辑</template>
          <el-form label-position="top">
            <el-form-item label="标题">
              <el-input v-model="form.title" maxlength="255" />
            </el-form-item>
            <el-form-item label="可见性">
              <el-select v-model="form.visibility" style="width: 100%">
                <el-option
                  v-for="option in VISIBILITIES"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </el-form-item>
            <el-button type="primary" :loading="saving" @click="save">
              保存
            </el-button>
            <el-button type="danger" plain @click="remove">删除</el-button>
          </el-form>
        </el-card>

        <el-card style="margin-top: 16px">
          <template #header>副本</template>
          <el-table :data="replicas" size="small">
            <el-table-column prop="backend" label="后端" />
            <el-table-column prop="state" label="状态" width="90" />
            <el-table-column label="主副本" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.is_primary" size="small" type="success">是</el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <HookSlot
          slot="image.detail"
          :context="{ sha: image.sha }"
          show-title
          style="margin-top: 16px"
        />
      </el-col>
    </el-row>
  </div>
</template>
