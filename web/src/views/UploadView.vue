<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api, errorMessage } from '@/api/client'
import HookSlot from '@/components/hook/HookSlot.vue'
import { useSessionStore } from '@/stores/session'
import { useSiteStore } from '@/stores/site'

const router = useRouter()
const session = useSessionStore()
const site = useSiteStore()

const albums = ref([])
const albumId = ref(null)
const uploaded = ref([])

function onExceed() {
  ElMessage.warning(`单次最多上传 ${site.uploadCountLimit} 个文件`)
}

async function loadAlbums() {
  if (!session.authenticated) {
    albums.value = []
    return
  }
  try {
    const data = await api.get('/albums')
    albums.value = data?.items || []
  } catch (error) {
    albums.value = []
  }
}

async function uploadFile(options) {
  const form = new FormData()
  form.append('file', options.file)
  if (albumId.value) form.append('album_id', String(albumId.value))

  try {
    const data = await api.post('/uploads', { form })
    if (data?.image) uploaded.value.unshift(data.image)
    ElMessage.success(`${options.file.name} 上传成功`)
    options.onSuccess?.(data)
  } catch (error) {
    if (error?.code === 'FORBIDDEN' && !session.authenticated) {
      ElMessage.error('站点未开放匿名上传，请先登录')
    } else {
      ElMessage.error(`${options.file.name} 上传失败：${errorMessage(error)}`)
    }
    options.onError?.(error)
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

onMounted(loadAlbums)
</script>

<template>
  <div class="upload-hero">
    <h1 class="upload-hero__title">上传图片</h1>
    <p class="upload-hero__desc">
      {{ site.uploadNotice || '拖拽、点击选择文件即可上传' }}
    </p>

    <el-alert
      v-if="!session.authenticated"
      class="upload-hero__tip"
      type="info"
      show-icon
      :closable="false"
      title="当前未登录"
    >
      <span>
        站点开放匿名上传时可直接上传；{{
          site.allowRegister ? '注册' : '登录'
        }}后可管理自己的图片。
      </span>
      <router-link :to="{ name: 'login', query: { redirect: '/' } }">登录</router-link>
    </el-alert>

    <div v-if="session.authenticated" class="upload-hero__toolbar">
      <el-select
        v-model="albumId"
        placeholder="默认相册"
        clearable
        style="width: 220px"
      >
        <el-option
          v-for="album in albums"
          :key="album.id"
          :label="album.name"
          :value="album.id"
        />
      </el-select>
    </div>

    <el-upload
      drag
      multiple
      :show-file-list="false"
      :http-request="uploadFile"
      :accept="site.uploadAccept"
      :limit="site.uploadCountLimit"
      :on-exceed="onExceed"
    >
      <div class="upload-zone__icon">
        <el-icon><UploadFilled /></el-icon>
      </div>
      <div class="upload-zone__text">拖拽文件到此处，或<em>点击选择</em></div>
      <div class="upload-zone__hint">
        支持{{ site.allowVideo ? '图片与视频' : '图片' }} · 单文件不超过
        {{ site.uploadMaxSize }} MB · 单次最多 {{ site.uploadCountLimit }} 个
      </div>
    </el-upload>

    <div v-if="uploaded.length" class="upload-results">
      <div v-for="item in uploaded" :key="item.sha" class="upload-result">
        <el-image class="upload-result__thumb" :src="item.src" fit="cover" />
        <div class="upload-result__body">
          <div class="upload-result__name">{{ item.filename }}</div>
          <div class="upload-result__link">{{ absolute(item.src) }}</div>
        </div>
        <el-button type="primary" plain size="small" @click="copy(absolute(item.src))">
          复制链接
        </el-button>
        <el-button
          size="small"
          text
          @click="router.push({ name: 'image-detail', params: { sha: item.sha } })"
        >
          详情
        </el-button>
      </div>
    </div>

    <HookSlot
      v-if="session.authenticated"
      slot="upload.after"
      show-title
      style="margin-top: 16px"
    />

    <div class="upload-hero__more">
      <el-button text @click="router.push({ name: 'images' })">浏览全部图片</el-button>
    </div>
  </div>
</template>
