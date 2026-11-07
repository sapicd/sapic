<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, errorMessage } from '@/api/client'
import HookSlot from '@/components/hook/HookSlot.vue'
import { useSiteStore } from '@/stores/site'
import { absoluteUrl, formatSize, formatTime } from '@/utils/format'

const VISIBILITY_LABELS = { public: '公开', private: '私有', shared: '共享' }
const VISIBILITY_TAGS = { public: 'success', private: 'info', shared: 'warning' }
//: 共享只存在于相册维度，单图只能覆盖为公开/私有（空值表示跟随相册）。
const VISIBILITIES = [
  { label: '公开', value: 'public' },
  { label: '私有', value: 'private' },
]

const route = useRoute()
const router = useRouter()
const site = useSiteStore()

const image = ref(null)
const replicas = ref([])
const loading = ref(false)
const saving = ref(false)
const form = reactive({
  title: '',
  visibility: '',
  tags: [],
  plaza: 'inherit',
  //: 有效期用 Date 驱动日期选择器，提交时换算成后端要的秒级时间戳。
  expireAt: null,
})

//: 生效可见性 = 单图覆盖，否则跟随相册（无相册时后端按公开处理）。
const effective = computed(() => {
  const own = image.value?.visibility
  if (own) return { value: own, follow: false }
  return { value: image.value?.album?.visibility || 'public', follow: true }
})
//: 只有作者和管理员能编辑；广场里点进来的公开图只读。
const canEdit = computed(() => Boolean(image.value?.can_edit))
const effectiveLabel = computed(() => VISIBILITY_LABELS[effective.value.value] || '未知')
const effectiveType = computed(() => VISIBILITY_TAGS[effective.value.value] || 'info')
const albumLabel = computed(() => VISIBILITY_LABELS[image.value?.album?.visibility] || '公开')
const visibilityOptions = computed(() => [
  { label: `跟随相册（${albumLabel.value}）`, value: '' },
  ...VISIBILITIES,
])

//: 广场三态：跟随相册 / 强制发布 / 强制排除，只有公开图片会真正出现在广场。
const plazaOptions = computed(() => [
  {
    label: `跟随相册（${image.value?.album?.plaza ? '已发布' : '未发布'}）`,
    value: 'inherit',
  },
  { label: '发布到广场', value: 'on' },
  { label: '不发布', value: 'off' },
])

async function load() {
  loading.value = true
  try {
    const data = await api.get(`/images/${route.params.sha}`)
    image.value = data?.image || null
    replicas.value = image.value?.replicas || []
    form.title = image.value?.title || ''
    //: 空串表示没有单图覆盖，可见性跟随相册。
    form.visibility = image.value?.visibility || ''
    form.tags = [...(image.value?.tags || [])]
    //: 单图的广场开关是三态，null 表示跟随相册。
    const plaza = image.value?.plaza
    form.plaza = plaza === null || plaza === undefined ? 'inherit' : plaza ? 'on' : 'off'
    form.expireAt = image.value?.expire_at
      ? new Date(image.value.expire_at * 1000)
      : null
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载图片失败'))
  } finally {
    loading.value = false
  }
}

//: 与后端同口径：不能设到过去；站点有上限时也不能超过上限。
function disabledExpireDate(date) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  if (date.getTime() < today.getTime()) return true
  const max = site.imageExpireMaxDays
  if (!max) return false
  return date.getTime() > Date.now() + max * 86400000
}

async function save() {
  saving.value = true
  try {
    const data = await api.patch(`/images/${route.params.sha}`, {
      json: {
        title: form.title,
        visibility: form.visibility || null,
        tags: form.tags,
        plaza: form.plaza === 'inherit' ? null : form.plaza === 'on',
        expire_at: form.expireAt
          ? Math.floor(form.expireAt.getTime() / 1000)
          : null,
      },
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

function openAlbum() {
  if (!image.value?.album) return
  router.push({ name: 'images', query: { album: image.value.album.id } })
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    ElMessage.warning('复制失败，请手动复制')
  }
}

//: 图片地址统一补成绝对地址，复制出去或在新标签打开才可用。
const srcUrl = computed(() => absoluteUrl(image.value?.src))

//: /raw/<sha> 是 sapic 的兜底出口（私有图、未配加速域名的本地存储），又长又没信息量，
//: 元数据里不展示地址本身，只留三种分享格式；复制地址仍可用顶部的「复制链接」。
const srcIsRaw = computed(() => {
  if (!srcUrl.value) return false
  try {
    return new URL(srcUrl.value).pathname.startsWith('/raw/')
  } catch (error) {
    return false
  }
})

function copy() {
  copyText(srcUrl.value)
}

//: 模板由后端按 v1 的 gen_url_tpl 生成；src 是相对地址时补全，复制出去才可用。
const shareFormats = computed(() => {
  const tpl = image.value?.tpl
  const src = image.value?.src || ''
  if (!tpl || !src) return []
  const absolute = absoluteUrl(src)
  const fix = (text) => {
    const value = String(text || '')
    return absolute !== src ? value.split(src).join(absolute) : value
  }
  return [
    { key: 'HTML', label: 'HTML', value: fix(tpl.HTML) },
    { key: 'Markdown', label: 'Markdown', value: fix(tpl.Markdown) },
    { key: 'rST', label: 'rST', value: fix(tpl.rST) },
  ].filter((item) => item.value)
})

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="page">
    <div class="page__header">
      <div class="page__heading">
        <h2 class="page__title">
          {{ image?.title || image?.filename || '图片详情' }}
        </h2>
        <div v-if="image?.title" class="page__subtitle">{{ image.filename }}</div>
      </div>
      <div class="detail-actions">
        <el-button :disabled="!image" @click="copy">复制链接</el-button>
        <el-button @click="router.push({ name: 'images' })">返回列表</el-button>
      </div>
    </div>

    <el-row v-if="image" :gutter="16">
      <el-col :xs="24" :md="14">
        <div class="detail-preview">
          <video
            v-if="image.is_video"
            :src="image.src"
            controls
            playsinline
            preload="metadata"
          />
          <el-image
            v-else
            :src="image.src"
            fit="contain"
            :preview-src-list="[absoluteUrl(image.src)]"
            preview-teleported
          />
        </div>
      </el-col>

      <el-col :xs="24" :md="10">
        <el-descriptions
          title="元数据"
          :column="1"
          :label-width="80"
          size="small"
          border
          class="detail-sheet"
        >
          <el-descriptions-item label="相册">
            <el-tag
              v-if="image.album"
              size="small"
              effect="plain"
              class="detail-album"
              title="查看该相册的图片"
              @click="openAlbum"
            >
              {{ image.album.name }} · {{ albumLabel }}
            </el-tag>
            <span v-else-if="image.album_id" class="detail-info__muted">
              所属相册不可见
            </span>
            <span v-else class="detail-info__muted">未归属</span>
          </el-descriptions-item>
          <el-descriptions-item label="可见性">
            <el-tag size="small" :type="effectiveType" effect="light">
              {{ effectiveLabel }}
            </el-tag>
            <span class="detail-info__muted">
              {{ effective.follow ? '跟随相册' : '单图覆盖' }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item v-if="site.plazaEnabled" label="广场">
            <el-tag
              size="small"
              :type="image.plaza_effective ? 'success' : 'info'"
              effect="plain"
            >
              {{ image.plaza_effective ? '已发布' : '未发布' }}
            </el-tag>
            <span class="detail-info__muted">
              {{ image.plaza === null || image.plaza === undefined ? '跟随相册' : '单图设置' }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="类型">
            {{ image.mime || '未知类型' }}
          </el-descriptions-item>
          <el-descriptions-item label="大小">
            {{ formatSize(image.size) }}
          </el-descriptions-item>
          <el-descriptions-item label="尺寸">
            <span v-if="image.width && image.height">
              {{ image.width }} × {{ image.height }}
            </span>
            <span v-else class="detail-info__muted">未知</span>
          </el-descriptions-item>
          <el-descriptions-item label="上传时间">
            {{ formatTime(image.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="过期时间">
            <span v-if="image.expire_at">{{ formatTime(image.expire_at) }}</span>
            <span v-else class="detail-info__muted">永久</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="image.tags?.length" label="标签">
            <div class="detail-info__tags">
              <el-tag
                v-for="tag in image.tags"
                :key="tag"
                size="small"
                type="success"
                effect="plain"
              >
                {{ tag }}
              </el-tag>
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="快捷链接">
            <div class="detail-link">
              <a
                v-if="srcUrl && !srcIsRaw"
                class="detail-link__url"
                :href="srcUrl"
                target="_blank"
                rel="noopener"
                :title="srcUrl"
              >
                {{ srcUrl }}
              </a>
              <div v-if="shareFormats.length" class="detail-link__formats">
                <el-link
                  v-for="item in shareFormats"
                  :key="item.key"
                  type="primary"
                  :underline="false"
                  @click="copyText(item.value)"
                >
                  {{ item.label }}
                </el-link>
              </div>
            </div>
          </el-descriptions-item>
        </el-descriptions>

        <el-descriptions
          v-if="replicas.length"
          title="副本"
          :column="1"
          :label-width="80"
          size="small"
          border
          class="detail-sheet detail-block"
        >
          <el-descriptions-item v-for="replica in replicas" :key="replica.backend">
            <!-- 对象路径占位太长，悬浮在副本名上提示，行内只保留状态 -->
            <template #label>
              <el-tooltip v-if="replica.key" :content="replica.key" placement="top">
                <span class="replica-label">{{ replica.backend }}</span>
              </el-tooltip>
              <span v-else>{{ replica.backend }}</span>
            </template>
            <el-tag
              size="small"
              :type="replica.state === 'ok' ? 'success' : 'info'"
              effect="plain"
            >
              {{ replica.state }}
            </el-tag>
            <span v-if="replica.is_primary" class="detail-info__muted">主副本</span>
            <span v-if="replica.size" class="detail-info__muted">
              {{ formatSize(replica.size) }}
            </span>
            <div v-if="replica.error" class="replica-meta replica-meta--error">
              {{ replica.error }}
            </div>
          </el-descriptions-item>
        </el-descriptions>

        <el-descriptions
          v-if="canEdit"
          title="编辑"
          :column="1"
          :label-width="80"
          size="small"
          border
          class="detail-sheet detail-block"
        >
          <el-descriptions-item label="标题">
            <el-input v-model="form.title" maxlength="255" />
          </el-descriptions-item>
          <el-descriptions-item label="标签">
            <el-select
              v-model="form.tags"
              multiple
              filterable
              allow-create
              default-first-option
              :reserve-keyword="false"
              :multiple-limit="10"
              placeholder="输入后回车添加，最多 10 个"
              style="width: 100%"
            />
          </el-descriptions-item>
          <el-descriptions-item label="可见性">
            <el-select v-model="form.visibility" style="width: 100%">
              <el-option
                v-for="option in visibilityOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </el-descriptions-item>
          <el-descriptions-item v-if="site.plazaEnabled" label="广场">
            <el-select v-model="form.plaza" style="width: 100%">
              <el-option
                v-for="option in plazaOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </el-descriptions-item>
          <el-descriptions-item label="有效期">
            <el-date-picker
              v-model="form.expireAt"
              type="datetime"
              placeholder="留空表示永久保留"
              :disabled-date="disabledExpireDate"
              clearable
              style="width: 100%"
            />
          </el-descriptions-item>
          <el-descriptions-item label="操作">
            <el-button type="primary" :loading="saving" @click="save">
              保存
            </el-button>
            <el-button type="danger" plain @click="remove">删除</el-button>
          </el-descriptions-item>
        </el-descriptions>

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
