<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, errorMessage } from '@/api/client'
import { useSessionStore } from '@/stores/session'
import { useSiteStore } from '@/stores/site'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const site = useSiteStore()

//: 每页数量选项：默认 15 张（每行 5 个正好 3 行），分页器上可切换。
const PAGE_SIZE_OPTIONS = [15, 30, 60, 90]

const items = ref([])
const albums = ref([])
const albumId = ref(null)
//: 管理员默认也只看自己的图库，点「显示全站图片」才切到全站视图。
const allImages = ref(false)
const keyword = ref('')
const tag = ref('')
const page = ref(1)
const pageSize = ref(15)
const total = ref(0)
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
//: 系统相册收纳匿名图，不属于任何人的图库：选中它就等于全站视图，
//: 否则列表必然是空的（后端对管理员按该系统相册筛选时也会自动放大口径）。
const scopeAll = computed(
  () => allImages.value || Boolean(activeAlbum.value?.is_system),
)
//: 最后一页的页码，用于判断右箭头还能不能往后翻。
const lastPage = computed(() =>
  Math.max(1, Math.ceil(total.value / (pageSize.value || 15))),
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

//: 请求序号：快速翻页或改每页数量时，后发的请求可能先回来，旧响应要丢弃。
let requestSeq = 0

async function load(target = page.value) {
  const seq = ++requestSeq
  loading.value = true
  try {
    const data = await api.get('/images', {
      query: {
        keyword: keyword.value,
        tag: tag.value.trim() || undefined,
        album_id: albumId.value || undefined,
        scope: scopeAll.value ? 'all' : undefined,
        page: target,
        page_size: pageSize.value,
      },
    })
    if (seq !== requestSeq) return
    items.value = data?.items || []
    total.value = Number(data?.total || 0)
    page.value = Number(data?.page || target)
  } catch (error) {
    if (seq !== requestSeq) return
    ElMessage.error(errorMessage(error, '加载图片失败'))
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

//: 重拉当前页；删空后自动退回上一页，避免停在空白页上。
async function reload() {
  await load(page.value)
  if (!items.value.length && page.value > 1) await load(page.value - 1)
}

//: 搜索条件变化一律回到第 1 页，否则会停在上一次的页码上。
function search() {
  clearSelection()
  return load(1)
}

//: 切换个人图库 / 全站图库，页码归零避免落在不存在的页上。
function toggleScope() {
  allImages.value = !allImages.value
  return search()
}

function changePage(target) {
  //: 批量选择只针对本页，翻页后清空可避免误操作到看不见的图片。
  clearSelection()
  load(target)
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

//: 每页数量变了，原先的页码没有意义，统一回到第 1 页。
function changeSize(size) {
  clearSelection()
  pageSize.value = Number(size) || pageSize.value
  page.value = 1
  load(1)
}

//: 光标在输入框/下拉里时方向键归控件自己用（移动光标、切换选项）。
function isEditable(target) {
  if (!target || !(target instanceof HTMLElement)) return false
  const tag = target.tagName
  return (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    tag === 'SELECT' ||
    target.isContentEditable
  )
}

//: Element Plus 的弹窗遮罩用 v-show 常驻 DOM（``display:none``），所以只能按
//: 可见性判断——直接查 ``.el-overlay`` 会让方向键永远被吞掉。
function overlayVisible() {
  return Array.from(document.querySelectorAll('.el-overlay')).some(
    (node) => node.getClientRects().length > 0,
  )
}

//: 左右方向键翻页，和分页器等价；到头就不再拦截，交给浏览器默认行为。
function onKeydown(event) {
  if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  if (isEditable(event.target)) return
  //: 弹窗（移动/导入/确认框）打开时方向键归弹窗用。
  if (moveDialog.value || importDialog.value) return
  if (overlayVisible()) return
  const target = page.value + (event.key === 'ArrowRight' ? 1 : -1)
  if (target < 1 || target > lastPage.value) return
  event.preventDefault()
  changePage(target)
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
    search()
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
    total.value = Math.max(total.value - 1, 0)
    ElMessage.success('已删除')
    //: 本页删空就回退一页，否则用户会停在空白页上。
    if (!items.value.length) await reload()
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
    await reload()
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
    total.value = Math.max(total.value - (data?.deleted || removed.size), 0)
    clearSelection()
    ElMessage.success(`已删除 ${data?.deleted || 0} 张`)
    if (!items.value.length) await reload()
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
      await search()
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
  window.addEventListener('keydown', onKeydown)
  albumId.value = albumFromQuery()
  await loadAlbums()
  await load(1)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="page">
    <div class="toolbar toolbar--filters">
      <el-button type="primary" @click="router.push({ name: 'upload' })">
        <el-icon><UploadFilled /></el-icon>
        <span>上传</span>
      </el-button>
      <el-button v-if="session.authenticated" @click="openImport">
        <el-icon><Link /></el-icon>
        <span>导入</span>
      </el-button>
      <el-button v-if="session.authenticated && !batchMode" @click="enterBatch">
        批量处理
      </el-button>
      <el-select
        v-if="session.authenticated"
        :model-value="albumId"
        class="toolbar__search toolbar__search--album"
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
      <el-tag v-if="activeAlbum" size="small" closable @close="selectAlbum(null)">
        {{ activeAlbum.name }}
      </el-tag>
      <el-tag
        v-if="scopeAll"
        size="small"
        type="warning"
        effect="plain"
        title="全站视图只显示公开图片"
      >
        全站（公开图）
      </el-tag>
      <el-input
        v-model="tag"
        class="toolbar__search toolbar__search--narrow"
        placeholder="按标签筛选"
        clearable
        @keyup.enter="search()"
        @clear="search()"
      />
      <el-input
        v-model="keyword"
        class="toolbar__search"
        placeholder="搜索文件名或标题"
        clearable
        @keyup.enter="search()"
        @clear="search()"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-button @click="search()">搜索</el-button>
      <el-button
        v-if="session.isAdmin && !activeAlbum?.is_system"
        :type="scopeAll ? 'primary' : ''"
        plain
        @click="toggleScope"
      >
        {{ scopeAll ? '只看我的图片' : '显示全站图片' }}
      </el-button>
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

    <div v-if="loading && !items.length" class="image-grid image-grid--five">
      <div v-for="n in 15" :key="n" class="image-skeleton">
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

    <div v-else class="image-grid image-grid--five">
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
            :src="item.thumb || item.src"
            muted
            playsinline
            preload="none"
          />
          <img
            v-else
            :src="item.thumb || item.src"
            :alt="item.title || item.filename"
            loading="lazy"
            decoding="async"
          />
          <span v-if="item.is_video" class="image-card__play" aria-hidden="true" />
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

    <div v-if="total" class="image-pager">
      <el-pagination
        :current-page="page"
        :page-size="pageSize"
        :page-sizes="PAGE_SIZE_OPTIONS"
        :total="total"
        layout="total, sizes, prev, pager, next, jumper"
        background
        @current-change="changePage"
        @size-change="changeSize"
      />
      <span class="image-pager__hint">← / → 翻页</span>
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
