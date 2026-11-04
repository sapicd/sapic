<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api, errorMessage } from '@/api/client'

const router = useRouter()

const items = ref([])
const cursor = ref(null)
const hasMore = ref(false)
const loading = ref(false)
const failed = ref('')

const isEmpty = computed(
  () => !loading.value && !failed.value && items.value.length === 0,
)

async function load(reset = true) {
  loading.value = true
  try {
    const data = await api.get('/plaza', {
      query: { limit: 24, cursor: reset ? undefined : cursor.value },
    })
    const page = data?.items || []
    items.value = reset ? page : [...items.value, ...page]
    cursor.value = data?.next_cursor || null
    hasMore.value = Boolean(data?.has_more)
    failed.value = ''
  } catch (error) {
    failed.value = errorMessage(error, '广场加载失败')
  } finally {
    loading.value = false
  }
}

function openDetail(item) {
  router.push({ name: 'image-detail', params: { sha: item.sha } })
}

function absolute(url) {
  return new URL(url, window.location.origin).toString()
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    ElMessage.warning('复制失败，请手动复制')
  }
}

onMounted(() => load(true))
</script>

<template>
  <div class="page">
    <div class="page__header">
      <h2 class="page__title">广场</h2>
      <span class="page__subtitle">仅展示作者主动发布的公开图片</span>
    </div>

    <el-alert
      v-if="failed"
      :title="failed"
      type="error"
      show-icon
      :closable="false"
    />

    <div v-else-if="loading && !items.length" class="image-grid">
      <div v-for="n in 8" :key="n" class="image-skeleton">
        <el-skeleton animated>
          <template #template>
            <el-skeleton-item
              variant="image"
              style="width: 100%; aspect-ratio: 4 / 3; border-radius: 12px"
            />
          </template>
        </el-skeleton>
      </div>
    </div>

    <el-empty v-else-if="isEmpty" description="广场还是空的，主动发布几张图片吧" />

    <div v-else class="image-grid">
      <div v-for="item in items" :key="item.sha" class="image-card">
        <div class="image-card__media" @click="openDetail(item)">
          <el-image
            :src="item.src"
            fit="cover"
            lazy
            style="width: 100%; height: 100%"
          />
          <div class="image-card__overlay" @click.stop>
            <el-button circle title="复制链接" @click="copy(absolute(item.src))">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
            <el-button circle title="查看详情" @click="openDetail(item)">
              <el-icon><View /></el-icon>
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
              v-for="name in (item.tags || []).slice(0, 2)"
              :key="name"
              size="small"
              type="success"
              effect="plain"
            >
              {{ name }}
            </el-tag>
          </div>
        </div>
      </div>
    </div>

    <div v-if="hasMore" class="load-more">
      <el-button round :loading="loading" @click="load(false)">加载更多</el-button>
    </div>
  </div>
</template>
