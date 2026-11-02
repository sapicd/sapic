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

const STATUS_TEXT = {
  ready: '待上传',
  uploading: '上传中',
  fail: '失败',
}

const albums = ref([])
const albumId = ref(null)
const fileList = ref([])
const uploading = ref(false)
const uploaded = ref([])

function onExceed() {
  ElMessage.warning(`单次最多上传 ${site.uploadCountLimit} 个文件`)
}

//: 新加入的文件默认跟随顶部「默认相册」，之后可逐个改成别的相册。
//: on-change 在文件加入时会触发，只在未赋值时写入，避免覆盖用户的逐个选择。
function onFileChange(file) {
  if (file.albumId === undefined || file.albumId === null) {
    file.albumId = albumId.value || null
  }
}

function removeFile(index) {
  fileList.value.splice(index, 1)
}

function clearFiles() {
  fileList.value = []
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

async function uploadOne(item) {
  item.status = 'uploading'
  const form = new FormData()
  form.append('file', item.raw)
  const target = item.albumId || albumId.value
  if (target) form.append('album_id', String(target))

  try {
    const data = await api.post('/uploads', { form })
    if (data?.image) uploaded.value.unshift(data.image)
    item.status = 'success'
    item.percentage = 100
    return true
  } catch (error) {
    item.status = 'fail'
    if (error?.code === 'FORBIDDEN' && !session.authenticated) {
      ElMessage.error('站点未开放匿名上传，请先登录')
    } else {
      ElMessage.error(`${item.name} 上传失败：${errorMessage(error)}`)
    }
    return false
  }
}

async function startUpload() {
  const pending = fileList.value.filter((item) => item.status !== 'success')
  if (!pending.length) {
    ElMessage.warning('请先选择文件')
    return
  }

  uploading.value = true
  let done = 0
  try {
    //: 逐个上传，避免一次并发全部请求把后端与带宽打满。
    for (const item of pending) {
      if (await uploadOne(item)) {
        const index = fileList.value.indexOf(item)
        if (index >= 0) fileList.value.splice(index, 1)
        done += 1
      }
    }
  } finally {
    uploading.value = false
  }
  if (done) ElMessage.success(`已上传 ${done} 个文件`)
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
      {{ site.uploadNotice || '拖拽或点击选择文件，选好后点「开始上传」' }}
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
      <span class="upload-hero__label">默认相册</span>
      <el-select
        v-model="albumId"
        placeholder="未指定（使用默认相册）"
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
      <span class="upload-hero__label upload-hero__label--hint">
        选中文件后可逐个修改
      </span>
    </div>

    <el-upload
      v-model:file-list="fileList"
      drag
      multiple
      :auto-upload="false"
      :disabled="uploading"
      :accept="site.uploadAccept"
      :limit="site.uploadCountLimit"
      :on-exceed="onExceed"
      :on-change="onFileChange"
    >
      <div class="upload-zone__icon">
        <el-icon><UploadFilled /></el-icon>
      </div>
      <div class="upload-zone__text">拖拽文件到此处，或<em>点击选择</em></div>
      <div class="upload-zone__hint">
        支持{{ site.allowVideo ? '图片与视频' : '图片' }} · 单文件不超过
        {{ site.uploadMaxSize }} MB · 单次最多 {{ site.uploadCountLimit }} 个
      </div>
      <div class="upload-zone__note">选择后不会自动上传，确认列表后点「开始上传」</div>

      <template #file="{ file, index }">
        <div class="upload-item">
          <span class="upload-item__name" :title="file.name">{{ file.name }}</span>
          <el-select
            v-if="session.authenticated"
            v-model="file.albumId"
            size="small"
            class="upload-item__album"
            placeholder="跟随默认相册"
            clearable
            :disabled="uploading"
          >
            <el-option
              v-for="album in albums"
              :key="album.id"
              :label="album.name"
              :value="album.id"
            />
          </el-select>
          <span class="upload-item__status">
            {{ STATUS_TEXT[file.status] || '' }}
          </span>
          <el-button
            link
            type="danger"
            size="small"
            :disabled="uploading"
            @click="removeFile(index)"
          >
            移除
          </el-button>
        </div>
      </template>
    </el-upload>

    <div class="upload-hero__toolbar">
      <el-button
        type="primary"
        :loading="uploading"
        :disabled="!fileList.length"
        @click="startUpload"
      >
        开始上传{{ fileList.length ? `（${fileList.length}）` : '' }}
      </el-button>
      <el-button :disabled="uploading || !fileList.length" @click="clearFiles">
        清空
      </el-button>
    </div>

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
  </div>
</template>
