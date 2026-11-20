<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api, errorMessage } from '@/api/client'
import { t } from '@/i18n'
import { useSiteStore } from '@/stores/site'
import { formatTime } from '@/utils/format'

const router = useRouter()
const site = useSiteStore()

const VISIBILITIES = computed(() => [
  { label: t('images.public'), value: 'public' },
  { label: t('images.private'), value: 'private' },
  { label: t('albums.shared'), value: 'shared' },
])

//: 可见性标签在表格里只显示，用函数按当前语言取词，省掉一份重复的映射表。
const VISIBILITY_KEYS = { public: 'images.public', private: 'images.private', shared: 'albums.shared' }

function visibilityText(value) {
  const key = VISIBILITY_KEYS[value]
  return key ? t(key) : value || ''
}

const PERMISSIONS = computed(() => [
  { label: t('albums.readOnly'), value: 'read' },
  { label: t('albums.writable'), value: 'write' },
])

const albums = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)
const form = reactive({
  name: '',
  description: '',
  visibility: 'private',
  plaza: false,
})

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
    ElMessage.error(errorMessage(error, t('albums.loadFailed')))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, {
    name: '',
    description: '',
    visibility: 'private',
    plaza: false,
  })
  dialogVisible.value = true
}

//: 私有相册添加成员时会自动升级为「共享」，所以私有相册也给入口；公开相册人人可见，无边授权。
function canShare(album) {
  return (
    album.role === 'owner' && !album.is_system && album.visibility !== 'public'
  )
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
    plaza: Boolean(album.plaza),
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
    ElMessage.success(t('albums.saved'))
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, t('albums.saveFailed')))
  } finally {
    saving.value = false
  }
}

async function remove(album) {
  try {
    await ElMessageBox.confirm(
      t('albums.deleteConfirm', { name: album.name }),
      t('albums.deleteTitle'),
      {
      type: 'warning',
    })
  } catch (error) {
    return
  }
  try {
    await api.del(`/albums/${album.id}`)
    ElMessage.success(t('common.deleted'))
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, t('albums.deleteFailed')))
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
    ElMessage.error(errorMessage(error, t('albums.sharesLoadFailed')))
  } finally {
    shareLoading.value = false
  }
}

async function addShare() {
  const username = shareForm.username.trim()
  if (!username) {
    ElMessage.warning(t('albums.memberRequired'))
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
    ElMessage.success(t('albums.shareAdded'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('albums.addFailed')))
  } finally {
    shareSaving.value = false
  }
}

async function updateSharePermission(member, permission) {
  if (!permission || permission === member.permission) return
  try {
    const data = await api.patch(
      `/albums/${shareAlbum.value.id}/shares/${member.user_id}`,
      { json: { permission } },
    )
    if (data?.share) Object.assign(member, data.share)
    ElMessage.success(t('albums.permUpdated'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('albums.permissionUpdatedFailed')))
    await loadShares()
  }
}

async function removeShare(member) {
  try {
    await ElMessageBox.confirm(
      t('albums.removeConfirm', { name: member.username }),
      t('albums.removeShareTitle'),
      { type: 'warning' },
    )
  } catch (error) {
    return
  }
  try {
    await api.del(`/albums/${shareAlbum.value.id}/shares/${member.user_id}`)
    await loadShares()
    ElMessage.success(t('albums.removed'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('albums.removeFailed')))
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="album-intro">
      <el-button type="primary" @click="openCreate">
        {{ t('albums.createTitle') }}
      </el-button>
      <p class="hint">{{ t('albums.intro') }}</p>
    </div>

    <el-card>
      <el-table
        v-loading="loading"
        :data="albums"
        size="small"
        :row-style="{ cursor: 'pointer' }"
        @row-click="openImages"
      >
        <el-table-column :label="t('albums.name')" min-width="180">
          <template #default="{ row }">
            <el-link type="primary" :underline="false">{{ row.name }}</el-link>
            <el-tag v-if="row.is_default" size="small" effect="plain" class="album-tag">
              {{ t('albums.isDefault') }}
            </el-tag>
            <el-tag
              v-if="row.is_system"
              size="small"
              type="info"
              effect="plain"
              class="album-tag"
            >
              {{ t('albums.isSystem') }}
            </el-tag>
            <el-tag
              v-if="row.role === 'shared'"
              size="small"
              type="warning"
              effect="plain"
              class="album-tag"
            >
              {{ t('albums.sharedByOthers') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="description"
          :label="t('albums.description')"
          min-width="200"
          show-overflow-tooltip
        />
        <el-table-column :label="t('albums.visibility')" width="100">
          <template #default="{ row }">
            {{ visibilityText(row.visibility) }}
          </template>
        </el-table-column>
        <el-table-column v-if="site.plazaEnabled" :label="t('nav.plaza')" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.plaza" size="small" type="success" effect="plain">
              {{ t('albums.published') }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="image_count" :label="t('albums.imageCount')" width="90" />
        <el-table-column :label="t('common.createdAt')" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column :label="t('common.actions')" width="200" align="right">
          <template #default="{ row }">
            <el-button
              v-if="canShare(row)"
              link
              type="primary"
              @click.stop="openShares(row)"
            >
              {{ t('albums.share') }}
            </el-button>
            <el-button
              link
              type="primary"
              :disabled="row.is_system"
              @click.stop="openEdit(row)"
            >
              {{ t('common.edit') }}
            </el-button>
            <el-button
              link
              type="danger"
              :disabled="row.is_default || row.is_system"
              @click.stop="remove(row)"
            >
              {{ t('common.delete') }}
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :description="t('albums.empty')" :image-size="60" />
        </template>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editing ? t('albums.editTitle') : t('albums.createTitle')"
      width="420px"
    >
      <el-form label-position="top">
        <el-form-item :label="t('albums.name')">
          <el-input v-model="form.name" maxlength="100" />
        </el-form-item>
        <el-form-item :label="t('albums.description')">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item :label="t('albums.visibility')">
          <el-select v-model="form.visibility" style="width: 100%">
            <el-option
              v-for="option in VISIBILITIES"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="site.plazaEnabled" :label="t('albums.publishToPlaza')">
          <el-switch v-model="form.plaza" />
          <span class="form-suffix">{{ t('albums.publishHint') }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="save">
          {{ t('common.save') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="shareVisible"
      :title="t('albums.shareTitle', { name: shareAlbum?.name || '' })"
      width="640px"
    >
      <p class="hint">{{ t('albums.shareIntro') }}</p>
      <div class="share-add">
        <el-input
          v-model="shareForm.username"
          :placeholder="t('albums.memberPlaceholder')"
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
          {{ t('albums.add') }}
        </el-button>
      </div>

      <el-table v-loading="shareLoading" :data="shares" size="small">
        <el-table-column prop="username" :label="t('albums.username')" min-width="120" />
        <el-table-column
          prop="nickname"
          :label="t('albums.nickname')"
          min-width="110"
          show-overflow-tooltip
        />
        <el-table-column :label="t('albums.permission')" width="130">
          <template #default="{ row }">
            <el-select
              :model-value="row.permission"
              size="small"
              @change="(value) => updateSharePermission(row, value)"
            >
              <el-option
                v-for="option in PERMISSIONS"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column :label="t('albums.addedAt')" width="160">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column :label="t('common.actions')" width="80" align="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="removeShare(row)">
              {{ t('common.remove') }}
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :description="t('albums.emptyShares')" :image-size="50" />
        </template>
      </el-table>

    </el-dialog>
  </div>
</template>
