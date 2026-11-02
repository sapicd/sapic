<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, errorMessage } from '@/api/client'
import { useSessionStore } from '@/stores/session'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const items = ref([])
const albums = ref([])
const albumId = ref(null)
const keyword = ref('')
const tag = ref('')
const cursor = ref(null)
const hasMore = ref(false)
const loading = ref(false)

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
        <el-button type="primary" @click="router.push({ name: 'upload' })">
          <el-icon><UploadFilled /></el-icon>
          <span>上传</span>
        </el-button>
      </div>
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
      <div v-for="item in items" :key="item.sha" class="image-card">
        <div class="image-card__media" @click="openDetail(item)">
          <el-image :src="item.src" fit="cover" lazy style="width: 100%; height: 100%" />
          <div class="image-card__overlay" @click.stop>
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
  </div>
</template>
