<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, errorMessage } from '@/api/client'
import { useSessionStore } from '@/stores/session'
import { useSiteStore } from '@/stores/site'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const site = useSiteStore()

const items = ref([])
const albums = ref([])
const albumId = ref(null)
const keyword = ref('')
const tag = ref('')
const cursor = ref(null)
const hasMore = ref(false)
const loading = ref(false)

//: 批量操作只针对当前已加载的图片，用 sha 数组保存选中项。
const selected = ref([])
//: 选择框与批量操作条默认隐藏，点了「批量处理」才进入多选模式。
const batchMode = ref(false)
const busy = ref(false)
const moveDialog = ref(false)
const moveTarget = ref(null)
const importDialog = ref(false)
const importText = ref('')
const importAlbum = ref(null)
const importing = ref(false)

const uploadableAlbums = computed(() =>
  albums.value.filter((album) => album.permission !== 'read'),
)

const isEmpty = computed(() => !loading.value && items.value.length === 0)
const activeAlbum = computed(
  () => albums.value.find((album) => album.id === albumId.value) || null,
)

//: 相册筛选走 URL（?album=ID），相册页跳过来时才能直接落到对应相册。
function albumFromQuery() {
  const raw = Array.isArray(route.query.album)
    ? route.query.album[0]
    : route.query.album
  const value = Number(raw)
  return Number.isInteger(value) && value > 0 ? value : null
}

async function loadAlbums() {
  if (!session.authenticated) return
  try {
    const data = await api.get('/albums')
    albums.value = data?.items || []
  } catch (error) {
    albums.value = []
  }
}

async function load(reset = true) {
  loading.value = true
  try {
    const data = await api.get('/images', {
      query: {
        keyword: keyword.value,
        tag: tag.value.trim() || undefined,
        album_id: albumId.value || undefined,
        limit: 24,
        cursor: reset ? undefined : cursor.value,
      },
    })
    const page = data?.items || []
    items.value = reset ? page : [...items.value, ...page]
    cursor.value = data?.next_cursor || null
    hasMore.value = Boolean(data?.has_more)
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载图片失败'))
  } finally {
    loading.value = false
  }
}

function selectAlbum(value) {
  const query = { ...route.query }
  if (value) query.album = String(value)
  else delete query.album
  router.replace({ name: 'images', query })
}

watch(
  () => route.query.album,
  () => {
    const next = albumFromQuery()
    if (next === albumId.value) return
    albumId.value = next
    load(true)
  },
)

function openDetail(item) {
  router.push({ name: 'image-detail', params: { sha: item.sha } })
}

async function remove(item) {
  try {
    await ElMessageBox.confirm(`确定删除 ${item.filename} 吗？`, '删除图片', {
      type: 'warning',
    })
  } catch (error) {
    return
  }
  try {
    await api.del(`/images/${item.sha}`)
    items.value = items.value.filter((row) => row.sha !== item.sha)
    ElMessage.success('已删除')
  } catch (error) {
    ElMessage.error(errorMessage(error, '删除失败'))
  }
}

function isSelected(sha) {
  return selected.value.includes(sha)
}

function enterBatch() {
  batchMode.value = true
}

function exitBatch() {
  batchMode.value = false
  clearSelection()
}

function toggleSelect(item) {
  selected.value = isSelected(item.sha)
    ? selected.value.filter((sha) => sha !== item.sha)
    : [...selected.value, item.sha]
}

//: 多选模式下点卡片是选中，其余情况才进详情页。
function handleCardClick(item) {
  if (batchMode.value) toggleSelect(item)
  else openDetail(item)
}

function selectAllLoaded() {
  selected.value = items.value.map((item) => item.sha)
}

function clearSelection() {
  selected.value = []
}

async function batchUpdate(payload, message) {
  if (!selected.value.length) return
  busy.value = true
  try {
    const data = await api.patch('/images/batch', {
      json: { shas: selected.value, ...payload },
    })
    clearSelection()
    await load(true)
    ElMessage.success(`${message}（${data?.updated || 0} 张）`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '批量操作失败'))
  } finally {
    busy.value = false
  }
}

function setVisibility(command) {
  //: 空值表示跟随相册，与单图编辑同口径。
  batchUpdate({ visibility: command === 'inherit' ? null : command }, '已更新可见性')
}

function setPlaza(command) {
  const value = command === 'inherit' ? null : command === 'publish'
  batchUpdate({ plaza: value }, '已更新广场状态')
}

async function moveSelected() {
  if (!moveTarget.value) {
    ElMessage.warning('请选择目标相册')
    return
  }
  await batchUpdate({ album_id: moveTarget.value }, '已移动到相册')
  moveDialog.value = false
  moveTarget.value = null
}

async function batchRemove() {
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selected.value.length} 张图片吗？外链登记的图片只删记录，不影响源站。`,
      '批量删除',
      { type: 'warning', confirmButtonText: '删除' },
    )
  } catch (error) {
    return
  }
  busy.value = true
  try {
    const data = await api.post('/images/batch/delete', {
      json: { shas: selected.value },
    })
    const removed = new Set(selected.value)
    items.value = items.value.filter((item) => !removed.has(item.sha))
    clearSelection()
    ElMessage.success(`已删除 ${data?.deleted || 0} 张`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '批量删除失败'))
  } finally {
    busy.value = false
  }
}

function openImport() {
  importText.value = ''
  importAlbum.value = null
  importDialog.value = true
}

async function runImport() {
  const links = [
    ...new Set(
      importText.value
        .split(/[\s,]+/)
        .map((line) => line.trim())
        .filter(Boolean),
    ),
  ]
  if (!links.length) {
    ElMessage.warning('请粘贴至少一个图片链接')
    return
  }
  importing.value = true
  try {
    const data = await api.post('/images/import', {
      json: { items: links, album_id: importAlbum.value || undefined },
    })
    const imported = data?.imported?.length || 0
    const failed = data?.failed || []
    if (imported) {
      ElMessage.success(`已导入 ${imported} 个外链`)
      importDialog.value = false
      await load(true)
    }
    if (failed.length) {
      const detail = failed
        .slice(0, 3)
        .map((item) => `${item.url}：${item.message}`)
        .join('；')
      ElMessage.warning(`${failed.length} 个链接未导入（${detail}）`)
    }
    if (!imported && !failed.length) ElMessage.info('没有可导入的链接')
  } catch (error) {
    ElMessage.error(errorMessage(error, '导入失败'))
  } finally {
    importing.value = false
  }
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    ElMessage.warning('复制失败，请手动复制')
  }
}

function absolute(url) {
  return new URL(url, window.location.origin).toString()
}

onMounted(async () => {
  albumId.value = albumFromQuery()
  await loadAlbums()
  await load(true)
})
</script>

<template>
  <div class="page">
    <div class="page__header">
      <h2 class="page__title">
        图片
        <el-tag
          v-if="activeAlbum"
          size="small"
          closable
          style="margin-left: 8px"
          @close="selectAlbum(null)"
        >
          {{ activeAlbum.name }}
        </el-tag>
      </h2>
      <div class="toolbar">
        <el-select
          v-if="session.authenticated"
          :model-value="albumId"
          class="toolbar__search"
          placeholder="全部相册"
          clearable
          @update:model-value="selectAlbum"
        >
          <el-option
            v-for="album in albums"
            :key="album.id"
            :label="album.name"
            :value="album.id"
          />
        </el-select>
        <el-input
          v-model="tag"
          class="toolbar__search toolbar__search--narrow"
          placeholder="按标签筛选"
          clearable
          @keyup.enter="load(true)"
          @clear="load(true)"
        />
        <el-input
          v-model="keyword"
          class="toolbar__search"
          placeholder="搜索文件名或标题"
          clearable
          @keyup.enter="load(true)"
          @clear="load(true)"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button @click="load(true)">搜索</el-button>
        <el-button v-if="session.authenticated && !batchMode" @click="enterBatch">
          批量处理
        </el-button>
        <el-button v-if="session.authenticated" @click="openImport">
          <el-icon><Link /></el-icon>
          <span>导入外链</span>
        </el-button>
        <el-button type="primary" @click="router.push({ name: 'upload' })">
          <el-icon><UploadFilled /></el-icon>
          <span>上传</span>
        </el-button>
      </div>
    </div>

    <div v-if="batchMode" class="bulk-bar">
      <span class="bulk-bar__count">已选 {{ selected.length }} 张</span>
      <el-button size="small" text @click="selectAllLoaded">全选本页</el-button>
      <el-button size="small" text :disabled="!selected.length" @click="clearSelection">
        清空
      </el-button>
      <el-divider direction="vertical" />
      <el-button
        size="small"
        :disabled="!selected.length"
        :loading="busy"
        @click="moveDialog = true"
      >
        移动到相册
      </el-button>
      <el-dropdown :disabled="!selected.length" @command="setVisibility">
        <el-button size="small" :disabled="!selected.length" :loading="busy">
          可见性
          <el-icon><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="public">公开</el-dropdown-item>
            <el-dropdown-item command="private">私有</el-dropdown-item>
            <el-dropdown-item command="inherit">跟随相册</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-dropdown v-if="site.plazaEnabled" :disabled="!selected.length" @command="setPlaza">
        <el-button size="small" :disabled="!selected.length" :loading="busy">
          广场
          <el-icon><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="publish">发布到广场</el-dropdown-item>
            <el-dropdown-item command="unpublish">取消发布</el-dropdown-item>
            <el-dropdown-item command="inherit">跟随相册</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button
        size="small"
        type="danger"
        :disabled="!selected.length"
        :loading="busy"
        @click="batchRemove"
      >
        删除
      </el-button>
      <el-button size="small" text class="bulk-bar__exit" @click="exitBatch">
        退出批量
      </el-button>
    </div>

    <div v-if="loading && !items.length" class="image-grid">
      <div v-for="n in 8" :key="n" class="image-skeleton">
        <el-skeleton animated>
          <template #template>
            <el-skeleton-item
              variant="image"
              style="width: 100%; aspect-ratio: 4 / 3; border-radius: 12px"
            />
            <div style="padding-top: 10px; display: flex; flex-direction: column; gap: 6px">
              <el-skeleton-item variant="text" style="width: 68%" />
              <el-skeleton-item variant="text" style="width: 38%" />
            </div>
          </template>
        </el-skeleton>
      </div>
    </div>

    <el-empty
      v-else-if="isEmpty"
      :description="albumId ? '该相册还没有图片' : '还没有图片'"
    >
      <el-button type="primary" @click="router.push({ name: 'upload' })">
        去上传
      </el-button>
    </el-empty>

    <div v-else class="image-grid">
      <div
        v-for="item in items"
        :key="item.sha"
        class="image-card"
        :class="{ 'is-selected': isSelected(item.sha) }"
      >
        <el-checkbox
          v-if="session.authenticated && batchMode"
          class="image-card__check"
          :model-value="isSelected(item.sha)"
          @change="toggleSelect(item)"
          @click.stop
        />
        <div class="image-card__media" @click="handleCardClick(item)">
          <video
            v-if="item.is_video"
            :src="item.src"
            muted
            playsinline
            preload="metadata"
          />
          <el-image
            v-else
            :src="item.src"
            fit="cover"
            lazy
            style="width: 100%; height: 100%"
          />
          <div v-if="!batchMode" class="image-card__overlay" @click.stop>
            <el-button circle title="复制链接" @click="copy(absolute(item.src))">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
            <el-button circle title="查看详情" @click="openDetail(item)">
              <el-icon><View /></el-icon>
            </el-button>
            <el-button
              v-if="session.authenticated"
              circle
              title="删除"
              @click="remove(item)"
            >
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>
        <div class="image-card__meta">
          <div class="image-card__name">{{ item.title || item.filename }}</div>
          <div class="image-card__sub">
            <el-tag v-if="item.is_video" size="small" type="warning" effect="plain">
              视频
            </el-tag>
            <el-tag v-if="item.external" size="small" type="info" effect="plain">
              外链
            </el-tag>
            <el-tag v-if="item.album" size="small" effect="plain">
              {{ item.album.name }}
            </el-tag>
            <el-tag
              v-if="item.visibility"
              size="small"
              type="warning"
              effect="plain"
            >
              {{ item.visibility }}
            </el-tag>
            <el-tag
              v-for="name in (item.tags || []).slice(0, 2)"
              :key="name"
              size="small"
              type="success"
              effect="plain"
            >
              {{ name }}
            </el-tag>
            <span v-if="(item.tags || []).length > 2" class="image-card__more">
              +{{ item.tags.length - 2 }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="hasMore" class="load-more">
      <el-button round :loading="loading" @click="load(false)">加载更多</el-button>
    </div>

    <el-dialog v-model="moveDialog" title="移动到相册" width="420px">
      <el-select v-model="moveTarget" placeholder="选择目标相册" style="width: 100%">
        <el-option
          v-for="album in uploadableAlbums"
          :key="album.id"
          :label="album.name"
          :value="album.id"
        />
      </el-select>
      <p class="hint">只能移动到你有写入权限的相册。</p>
      <template #footer>
        <el-button @click="moveDialog = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="moveSelected">移动</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importDialog" title="导入外链图片" width="560px">
      <el-form label-position="top">
        <el-form-item label="图片链接（一行一个，也可用空格、逗号分隔）">
          <el-input
            v-model="importText"
            type="textarea"
            :rows="6"
            placeholder="https://example.com/a.png"
          />
        </el-form-item>
        <el-form-item label="归入相册（可选）">
          <el-select v-model="importAlbum" placeholder="默认相册" clearable style="width: 100%">
            <el-option
              v-for="album in uploadableAlbums"
              :key="album.id"
              :label="album.name"
              :value="album.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <p class="hint">
        外链只登记地址，不下载文件、不占存储；公开相册里的图片直接展示源站地址，私有图片由本站转发。
        删除记录不会影响源站。
      </p>
      <template #footer>
        <el-button @click="importDialog = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="runImport">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>
