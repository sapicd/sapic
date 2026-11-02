<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api, errorMessage } from '@/api/client'
import { formatTime } from '@/utils/format'

const router = useRouter()

const VISIBILITIES = [
  { label: '公开', value: 'public' },
  { label: '私有', value: 'private' },
  { label: '共享', value: 'shared' },
]

const VISIBILITY_TEXT = {
  public: '公开',
  private: '私有',
  shared: '共享',
}

const PERMISSIONS = [
  { label: '只读', value: 'read' },
  { label: '可编辑（预留）', value: 'write' },
]

const PERMISSION_TEXT = { read: '只读', write: '可编辑' }

const albums = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)
const form = reactive({ name: '', description: '', visibility: 'private' })

const shareVisible = ref(false)
const shareAlbum = ref(null)
const shares = ref([])
const shareLoading = ref(false)
const shareSaving = ref(false)
const shareForm = reactive({ username: '', permission: 'read' })

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

function openImages(album) {
  //: 图片页通过 ?album=ID 读取筛选条件，跳过去即可看到该相册的内容。
  router.push({ name: 'images', query: { album: album.id } })
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

function openShares(album) {
  shareAlbum.value = album
  shares.value = []
  shareForm.username = ''
  shareForm.permission = 'read'
  shareVisible.value = true
  loadShares()
}

async function loadShares() {
  if (!shareAlbum.value) return
  shareLoading.value = true
  try {
    const data = await api.get(`/albums/${shareAlbum.value.id}/shares`)
    shares.value = data?.items || []
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载共享成员失败'))
  } finally {
    shareLoading.value = false
  }
}

async function addShare() {
  const username = shareForm.username.trim()
  if (!username) {
    ElMessage.warning('请输入成员用户名')
    return
  }
  shareSaving.value = true
  try {
    const data = await api.post(`/albums/${shareAlbum.value.id}/shares`, {
      json: { username, permission: shareForm.permission },
    })
    //: 后端可能把「私有」提升为「共享」，直接同步到表格里的这一行。
    if (data?.album) Object.assign(shareAlbum.value, data.album)
    shareForm.username = ''
    await loadShares()
    ElMessage.success('已添加共享成员')
  } catch (error) {
    ElMessage.error(errorMessage(error, '添加失败'))
  } finally {
    shareSaving.value = false
  }
}

async function removeShare(member) {
  try {
    await ElMessageBox.confirm(
      `确定移除成员「${member.username}」吗？`,
      '移除共享成员',
      { type: 'warning' },
    )
  } catch (error) {
    return
  }
  try {
    await api.del(`/albums/${shareAlbum.value.id}/shares/${member.user_id}`)
    await loadShares()
    ElMessage.success('已移除')
  } catch (error) {
    ElMessage.error(errorMessage(error, '移除失败'))
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
      「共享」相册只对你在「共享」里绑定的成员可见，私有相册添加成员后会自动变成共享。
    </p>

    <el-card>
      <el-table
        v-loading="loading"
        :data="albums"
        size="small"
        :row-style="{ cursor: 'pointer' }"
        @row-click="openImages"
      >
        <el-table-column label="名称" min-width="180">
          <template #default="{ row }">
            <el-link type="primary" :underline="false">{{ row.name }}</el-link>
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
            <el-tag
              v-if="row.role === 'shared'"
              size="small"
              type="warning"
              effect="plain"
              class="album-tag"
            >
              他人共享
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="description"
          label="描述"
          min-width="200"
          show-overflow-tooltip
        />
        <el-table-column label="可见性" width="100">
          <template #default="{ row }">
            {{ VISIBILITY_TEXT[row.visibility] || row.visibility }}
          </template>
        </el-table-column>
        <el-table-column prop="image_count" label="图片数" width="90" />
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" align="right">
          <template #default="{ row }">
            <el-button
              v-if="row.role === 'owner' && !row.is_system"
              link
              type="primary"
              @click.stop="openShares(row)"
            >
              共享
            </el-button>
            <el-button
              link
              type="primary"
              :disabled="row.is_system"
              @click.stop="openEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              link
              type="danger"
              :disabled="row.is_default || row.is_system"
              @click.stop="remove(row)"
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

    <el-dialog
      v-model="shareVisible"
      :title="`共享成员 · ${shareAlbum?.name || ''}`"
      width="520px"
    >
      <p class="hint">
        按用户名绑定站点成员；「共享」相册仅成员可见，「公开」相册本来就对所有人可见，成员设置不影响公开访问。
      </p>
      <div class="share-add">
        <el-input
          v-model="shareForm.username"
          placeholder="成员用户名"
          clearable
          @keyup.enter="addShare"
        />
        <el-select v-model="shareForm.permission" style="width: 150px">
          <el-option
            v-for="option in PERMISSIONS"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
        <el-button type="primary" :loading="shareSaving" @click="addShare">
          添加
        </el-button>
      </div>

      <el-table v-loading="shareLoading" :data="shares" size="small">
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="nickname" label="昵称" min-width="110" show-overflow-tooltip />
        <el-table-column label="权限" width="90">
          <template #default="{ row }">
            {{ PERMISSION_TEXT[row.permission] || row.permission }}
          </template>
        </el-table-column>
        <el-table-column label="添加时间" width="160">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="removeShare(row)">移除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="还没有共享成员" :image-size="50" />
        </template>
      </el-table>
    </el-dialog>
  </div>
</template>
