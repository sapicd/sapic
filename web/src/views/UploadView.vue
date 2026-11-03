<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
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

//: 粘贴得来的文件常常没有文件名或扩展名（如截图），按 MIME 补全，后端按后缀校验白名单。
const MIME_EXT = {
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/gif': 'gif',
  'image/webp': 'webp',
  'image/bmp': 'bmp',
  'image/svg+xml': 'svg',
  'image/x-icon': 'ico',
  'video/mp4': 'mp4',
  'video/webm': 'webm',
  'video/quicktime': 'mov',
  'video/x-m4v': 'm4v',
  'video/x-msvideo': 'avi',
}

const uploadRef = ref(null)
const albums = ref([])
const albumId = ref(null)
const fileList = ref([])
const urlList = ref([])
const uploading = ref(false)
const uploaded = ref([])

const pendingTotal = computed(() => fileList.value.length + urlList.value.length)

//: 文件与链接共用单次上传数量上限。
function remainingSlots() {
  return Math.max(site.uploadCountLimit - pendingTotal.value, 0)
}

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

//: 与 el-upload 的 accept 口径一致：既支持扩展名，也支持 image/* 这类通配。
function isAccepted(name, type) {
  const mime = (type || '').toLowerCase()
  return site.uploadAccept.split(',').some((item) => {
    const rule = item.trim().toLowerCase()
    if (!rule) return false
    if (rule.endsWith('/*')) return mime.startsWith(rule.slice(0, -1))
    return name.toLowerCase().endsWith(rule)
  })
}

function pasteName(raw) {
  const name = raw.name || ''
  if (/\.[^./\\]+$/.test(name)) return name
  const ext = MIME_EXT[(raw.type || '').toLowerCase()] || ''
  return `pasted-${Date.now()}${ext ? `.${ext}` : ''}`
}

//: 粘贴的文件交回 el-upload 托管，才能复用数量限制、on-change 与列表渲染。
function onPaste(event) {
  const data = event.clipboardData
  if (!data) return
  let raws = []
  for (const item of data.items) {
    if (item.kind !== 'file') continue
    const raw = item.getAsFile()
    if (raw) raws.push(raw)
  }
  //: 部分浏览器只把文件放在 files 里，items 拿不到，这里兜底。
  if (!raws.length && data.files?.length) raws = [...data.files]

  if (!raws.length) {
    //: 纯文本粘贴：只接管图片链接，输入框里的粘贴与普通文本照常处理。
    if (isEditableTarget(event.target)) return
    const url = parseImageUrl((data.getData('text/plain') || '').trim())
    if (!url) return
    event.preventDefault()
    addUrl(url)
    return
  }
  event.preventDefault()
  if (uploading.value) {
    ElMessage.warning('正在上传，请稍后再粘贴')
    return
  }

  const room = remainingSlots()
  if (!room) {
    ElMessage.warning(`单次最多上传 ${site.uploadCountLimit} 个文件`)
    return
  }
  const pending = raws.slice(0, room)
  if (pending.length < raws.length) {
    ElMessage.warning(`单次最多上传 ${site.uploadCountLimit} 个文件，多余的已忽略`)
  }

  let added = 0
  for (const raw of pending) {
    const name = pasteName(raw)
    if (!isAccepted(name, raw.type)) {
      ElMessage.warning(`不支持粘贴该类型的文件：${name}`)
      continue
    }
    uploadRef.value?.handleStart(new File([raw], name, { type: raw.type }))
    added += 1
  }
  if (added) ElMessage.success(`已加入 ${added} 个粘贴的文件`)
}

function isEditableTarget(target) {
  const tag = target?.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || Boolean(target?.isContentEditable)
}

//: 只接管后缀在白名单内的链接，普通网页链接照常按文本处理。
function parseImageUrl(text) {
  if (!text || /\s/.test(text)) return null
  let url
  try {
    url = new URL(text)
  } catch (error) {
    return null
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
  if (!isAccepted(url.pathname, '')) return null
  return url
}

function urlName(url) {
  const last = url.pathname.split('/').pop() || ''
  try {
    return decodeURIComponent(last) || url.hostname
  } catch (error) {
    return last || url.hostname
  }
}

//: 链接不上传到浏览器，只登记 URL，由后端抓取，避免跨域与防盗链问题。
function addUrl(url) {
  if (uploading.value) {
    ElMessage.warning('正在上传，请稍后再粘贴')
    return
  }
  if (!remainingSlots()) {
    ElMessage.warning(`单次最多上传 ${site.uploadCountLimit} 个文件`)
    return
  }
  const href = url.toString()
  if (urlList.value.some((item) => item.url === href)) {
    ElMessage.info('该链接已在待上传列表中')
    return
  }
  urlList.value.push({ url: href, name: urlName(url), status: 'ready' })
  ElMessage.success('已加入待上传列表')
}

function removeUrl(index) {
  urlList.value.splice(index, 1)
}

function removeFile(index) {
  fileList.value.splice(index, 1)
}

function clearFiles() {
  fileList.value = []
  urlList.value = []
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

async function uploadRemote(item) {
  item.status = 'uploading'
  const form = new FormData()
  form.append('url', item.url)
  if (albumId.value) form.append('album_id', String(albumId.value))

  try {
    const data = await api.post('/uploads', { form })
    if (data?.image) uploaded.value.unshift(data.image)
    item.status = 'success'
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
  const pendingFiles = fileList.value.filter((item) => item.status !== 'success')
  const pendingUrls = urlList.value.filter((item) => item.status !== 'success')
  if (!pendingFiles.length && !pendingUrls.length) {
    ElMessage.warning('请先选择文件或粘贴图片链接')
    return
  }

  uploading.value = true
  let done = 0
  try {
    //: 逐个上传，避免一次并发全部请求把后端与带宽打满。
    for (const item of pendingFiles) {
      if (await uploadOne(item)) {
        const index = fileList.value.indexOf(item)
        if (index >= 0) fileList.value.splice(index, 1)
        done += 1
      }
    }
    for (const item of pendingUrls) {
      if (await uploadRemote(item)) {
        const index = urlList.value.indexOf(item)
        if (index >= 0) urlList.value.splice(index, 1)
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

onMounted(() => {
  loadAlbums()
  //: 首页任意位置粘贴即可加入待上传列表，不要求焦点落在上传区。
  window.addEventListener('paste', onPaste)
})

onBeforeUnmount(() => {
  window.removeEventListener('paste', onPaste)
})
</script>

<template>
  <div class="upload-hero">
    <h1 class="upload-hero__title">上传图片</h1>
    <p class="upload-hero__desc">
      {{ site.uploadNotice || '拖拽、点击选择或粘贴图片/链接，选好后点「开始上传」' }}
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
      ref="uploadRef"
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
      <div class="upload-zone__text">拖拽文件到此处，或<em>点击选择</em>、粘贴图片</div>
      <div class="upload-zone__hint">
        支持{{ site.allowVideo ? '图片与视频' : '图片' }} · 单文件不超过
        {{ site.uploadMaxSize }} MB · 单次最多 {{ site.uploadCountLimit }} 个
      </div>
      <div class="upload-zone__note">
        支持 Ctrl/⌘ + V 粘贴图片或图片链接，加入列表后点「开始上传」
      </div>

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

    <div v-if="urlList.length" class="upload-remote">
      <div v-for="(item, index) in urlList" :key="item.url" class="upload-item">
        <el-tag size="small" type="info">URL</el-tag>
        <span class="upload-item__name" :title="item.url">{{ item.name }}</span>
        <span class="upload-item__status">
          {{ STATUS_TEXT[item.status] || '' }}
        </span>
        <el-button
          link
          type="danger"
          size="small"
          :disabled="uploading"
          @click="removeUrl(index)"
        >
          移除
        </el-button>
      </div>
    </div>

    <div class="upload-hero__toolbar">
      <el-button
        type="primary"
        :loading="uploading"
        :disabled="!pendingTotal"
        @click="startUpload"
      >
        开始上传{{ pendingTotal ? `（${pendingTotal}）` : '' }}
      </el-button>
      <el-button :disabled="uploading || !pendingTotal" @click="clearFiles">
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
