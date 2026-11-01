<script setup>
import { onMounted, reactive, ref } from 'vue'

import { api, errorMessage } from '@/api/client'
import { formatTime } from '@/utils/format'

const VISIBILITIES = [
  { label: '公开', value: 'public' },
  { label: '私有', value: 'private' },
  { label: '共享', value: 'shared' },
]

const albums = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)
const form = reactive({ name: '', description: '', visibility: 'private' })

async function load() {
  loading.value = true
  try {
    const data = await api.get('/albums')
    albums.value = data?.items || []
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载相册失败'))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, { name: '', description: '', visibility: 'private' })
  dialogVisible.value = true
}

function openEdit(album) {
  editing.value = album
  Object.assign(form, {
    name: album.name,
    description: album.description || '',
    visibility: album.visibility || 'private',
  })
  dialogVisible.value = true
}

async function save() {
  saving.value = true
  try {
    if (editing.value) {
      await api.patch(`/albums/${editing.value.id}`, { json: { ...form } })
    } else {
      await api.post('/albums', { json: { ...form } })
    }
    dialogVisible.value = false
    ElMessage.success('已保存')
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '保存失败'))
  } finally {
    saving.value = false
  }
}

async function remove(album) {
  try {
    await ElMessageBox.confirm(`确定删除相册「${album.name}」吗？`, '删除相册', {
      type: 'warning',
    })
  } catch (error) {
    return
  }
  try {
    await api.del(`/albums/${album.id}`)
    ElMessage.success('已删除')
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '删除失败（相册非空时无法删除）'))
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page__header">
      <h2 class="page__title">相册</h2>
      <el-button type="primary" @click="openCreate">新建相册</el-button>
    </div>

    <p class="hint">
      图片可见性以相册为单位；上传时未指定相册的图片会进入「默认相册」，单张图片可在详情页覆盖。
    </p>

    <el-card>
      <el-table v-loading="loading" :data="albums" size="small">
        <el-table-column label="名称" min-width="180">
          <template #default="{ row }">
            <span>{{ row.name }}</span>
            <el-tag v-if="row.is_default" size="small" effect="plain" class="album-tag">
              默认
            </el-tag>
            <el-tag
              v-if="row.is_system"
              size="small"
              type="info"
              effect="plain"
              class="album-tag"
            >
              系统
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="visibility" label="可见性" width="100" />
        <el-table-column prop="image_count" label="图片数" width="90" />
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="right">
          <template #default="{ row }">
            <el-button link type="primary" :disabled="row.is_system" @click="openEdit(row)">
              编辑
            </el-button>
            <el-button
              link
              type="danger"
              :disabled="row.is_default || row.is_system"
              @click="remove(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="还没有相册" :image-size="60" />
        </template>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑相册' : '新建相册'"
      width="420px"
    >
      <el-form label-position="top">
        <el-form-item label="名称">
          <el-input v-model="form.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" />
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
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
