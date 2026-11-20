<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, errorMessage } from '@/api/client'
import HookSlot from '@/components/hook/HookSlot.vue'
import { t } from '@/i18n'
import { useSiteStore } from '@/stores/site'
import { albumName } from '@/utils/album'
import { absoluteUrl, formatSize, formatTime } from '@/utils/format'

//: 可见性文案复用 images / albums 的词条，避免同一批枚举出现两套说法。
const VISIBILITY_KEYS = { public: 'images.public', private: 'images.private', shared: 'albums.shared' }
const VISIBILITY_TAGS = { public: 'success', private: 'info', shared: 'warning' }

function visibilityLabel(value) {
  const key = VISIBILITY_KEYS[value]
  return key ? t(key) : ''
}

//: 共享只存在于相册维度，单图只能覆盖为公开/私有（空值表示跟随相册）。
const VISIBILITIES = computed(() => [
  { label: t('images.public'), value: 'public' },
  { label: t('images.private'), value: 'private' },
])

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
const effectiveLabel = computed(
  () => visibilityLabel(effective.value.value) || t('common.unknown'),
)
const effectiveType = computed(() => VISIBILITY_TAGS[effective.value.value] || 'info')
const albumLabel = computed(
  () => visibilityLabel(image.value?.album?.visibility) || t('images.public'),
)
const visibilityOptions = computed(() => [
  { label: t('detail.followAlbumWith', { label: albumLabel.value }), value: '' },
  ...VISIBILITIES.value,
])

//: 广场三态：跟随相册 / 强制发布 / 强制排除，只有公开图片会真正出现在广场。
const plazaOptions = computed(() => [
  {
    label: t('detail.followAlbumWith', {
      label: image.value?.album?.plaza ? t('detail.plazaPublished') : t('detail.plazaUnpublished'),
    }),
    value: 'inherit',
  },
  { label: t('albums.publishToPlaza'), value: 'on' },
  { label: t('detail.doNotPublish'), value: 'off' },
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
    ElMessage.error(errorMessage(error, t('images.loadFailed')))
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
    ElMessage.success(t('albums.saved'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('albums.saveFailed')))
  } finally {
    saving.value = false
  }
}

async function remove() {
  try {
    await ElMessageBox.confirm(
      t('detail.deleteConfirm'),
      t('images.deleteTitle'),
      {
      type: 'warning',
    })
  } catch (error) {
    return
  }
  try {
    await api.del(`/images/${route.params.sha}`)
    ElMessage.success(t('common.deleted'))
    router.push({ name: 'images' })
  } catch (error) {
    ElMessage.error(errorMessage(error, t('images.deleteFailed')))
  }
}

function openAlbum() {
  if (!image.value?.album) return
  router.push({ name: 'images', query: { album: image.value.album.id } })
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success(t('common.copiedToast'))
  } catch (error) {
    ElMessage.warning(t('common.copyFailed'))
  }
}

//: 图片地址统一补成绝对地址，复制出去或在新标签打开才可用。
const srcUrl = computed(() => absoluteUrl(image.value?.src))

function copy() {
  copyText(srcUrl.value)
}

//: /raw/<sha> 是 sapic 的出口，出现它有两种原因：私有图必须靠它鉴权，
//: 公开图则是后端没配加速域名（本地存储常见）。
const srcIsRaw = computed(() => {
  if (!srcUrl.value) return false
  try {
    return new URL(srcUrl.value).pathname.startsWith('/raw/')
  } catch (error) {
    return false
  }
})

const linkHint = computed(() => {
  if (!srcIsRaw.value) return ''
  //: 非公开图（私有 / 共享）的 /raw 是鉴权出口；公开图回落 /raw 则是出不了直链。
  return effective.value.value === 'public'
    ? t('detail.proxyHint')
    : t('detail.privateHint')
})

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
          {{ image?.title || image?.filename || t('detail.title') }}
        </h2>
        <div v-if="image?.title" class="page__subtitle">{{ image.filename }}</div>
      </div>
      <div class="detail-actions">
        <el-button :disabled="!image" @click="copy">{{ t('common.copyLink') }}</el-button>
        <el-button @click="router.push({ name: 'images' })">
          {{ t('detail.backToList') }}
        </el-button>
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
          :title="t('detail.meta')"
          :column="1"
          :label-width="80"
          size="small"
          border
          class="detail-sheet"
        >
          <el-descriptions-item :label="t('detail.album')">
            <el-tag
              v-if="image.album"
              size="small"
              effect="plain"
              class="detail-album"
              :title="t('detail.viewAlbumImages')"
              @click="openAlbum"
            >
              {{ albumName(image.album) }} · {{ albumLabel }}
            </el-tag>
            <span v-else-if="image.album_id" class="detail-info__muted">
              {{ t('detail.albumNotVisible') }}
            </span>
            <span v-else class="detail-info__muted">{{ t('detail.noAlbum') }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('images.visibility')">
            <el-tag size="small" :type="effectiveType" effect="light">
              {{ effectiveLabel }}
            </el-tag>
            <span class="detail-info__muted">
              {{ effective.follow ? t('images.followAlbum') : t('detail.singleOverride') }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item v-if="site.plazaEnabled" :label="t('nav.plaza')">
            <el-tag
              size="small"
              :type="image.plaza_effective ? 'success' : 'info'"
              effect="plain"
            >
              {{
                image.plaza_effective ? t('detail.plazaPublished') : t('detail.plazaUnpublished')
              }}
            </el-tag>
            <span class="detail-info__muted">
              {{
                image.plaza === null || image.plaza === undefined
                  ? t('images.followAlbum')
                  : t('detail.singleSetting')
              }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('images.type')">
            {{ image.mime || t('detail.unknownType') }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('detail.size')">
            {{ formatSize(image.size) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('detail.dimensions')">
            <span v-if="image.width && image.height">
              {{ image.width }} × {{ image.height }}
            </span>
            <span v-else class="detail-info__muted">{{ t('common.unknown') }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('detail.uploadedAt')">
            {{ formatTime(image.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('detail.expiresAt')">
            <span v-if="image.expire_at">{{ formatTime(image.expire_at) }}</span>
            <span v-else class="detail-info__muted">{{ t('upload.forever') }}</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="image.tags?.length" :label="t('detail.tags')">
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
          <el-descriptions-item :label="t('detail.quickLinks')">
            <!--: 只放分享格式：地址本身太长（又拍云直链也一样），复制地址走顶部「复制链接」。 -->
            <div class="detail-link">
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
            <p v-if="linkHint" class="detail-link__hint">{{ linkHint }}</p>
          </el-descriptions-item>
        </el-descriptions>

        <el-descriptions
          v-if="replicas.length"
          :title="t('detail.replicas')"
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
            <span v-if="replica.is_primary" class="detail-info__muted">
              {{ t('detail.primaryReplica') }}
            </span>
            <span v-if="replica.size" class="detail-info__muted">
              {{ formatSize(replica.size) }}
            </span>
            <!--: 只有匿名可读的副本才有直链；私有桶 / 未配加速域名统一走 /raw。 -->
            <el-tooltip
              v-if="replica.link"
              :content="replica.link"
              placement="top"
            >
              <el-link
                class="replica-copy"
                type="primary"
                :underline="false"
                @click="copyText(replica.link)"
              >
                {{ t('detail.copyReplicaLink') }}
              </el-link>
            </el-tooltip>
            <el-tooltip
              v-else
              :content="t('detail.replicaPrivateHint')"
              placement="top"
            >
              <span class="replica-copy replica-copy--empty">
                {{ t('detail.noDirectLink') }}
              </span>
            </el-tooltip>
            <div v-if="replica.error" class="replica-meta replica-meta--error">
              {{ replica.error }}
            </div>
          </el-descriptions-item>
        </el-descriptions>

        <el-descriptions
          v-if="canEdit"
          :title="t('detail.edit')"
          :column="1"
          :label-width="80"
          size="small"
          border
          class="detail-sheet detail-block"
        >
          <el-descriptions-item :label="t('detail.titleLabel')">
            <el-input v-model="form.title" maxlength="255" />
          </el-descriptions-item>
          <el-descriptions-item :label="t('detail.tags')">
            <el-select
              v-model="form.tags"
              multiple
              filterable
              allow-create
              default-first-option
              :reserve-keyword="false"
              :multiple-limit="10"
              :placeholder="t('detail.tagPlaceholder')"
              style="width: 100%"
            />
          </el-descriptions-item>
          <el-descriptions-item :label="t('images.visibility')">
            <el-select v-model="form.visibility" style="width: 100%">
              <el-option
                v-for="option in visibilityOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </el-descriptions-item>
          <el-descriptions-item v-if="site.plazaEnabled" :label="t('nav.plaza')">
            <el-select v-model="form.plaza" style="width: 100%">
              <el-option
                v-for="option in plazaOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </el-descriptions-item>
          <el-descriptions-item :label="t('upload.expire')">
            <el-date-picker
              v-model="form.expireAt"
              type="datetime"
              :placeholder="t('detail.expirePlaceholder')"
              :disabled-date="disabledExpireDate"
              clearable
              style="width: 100%"
            />
          </el-descriptions-item>
          <el-descriptions-item :label="t('common.actions')">
            <el-button type="primary" :loading="saving" @click="save">
              {{ t('common.save') }}
            </el-button>
            <el-button type="danger" plain @click="remove">
              {{ t('common.delete') }}
            </el-button>
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
