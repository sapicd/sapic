<script setup>
import { computed, onMounted, ref } from 'vue'

import { api, errorMessage } from '@/api/client'
import { t } from '@/i18n'
import { useSessionStore } from '@/stores/session'
import { formatTime } from '@/utils/format'

//: 状态与筛选项都随语言切换，所以用 computed 而不是模块级常量。
const STATUS_META = computed(() => ({
  '-2': { label: t('users.statusRejected'), type: 'info' },
  '-1': { label: t('users.statusPending'), type: 'warning' },
  0: { label: t('users.statusDisabled'), type: 'danger' },
  1: { label: t('users.statusActive'), type: 'success' },
}))

const STATUS_FILTERS = computed(() => [
  { label: t('users.allStatuses'), value: '' },
  { label: t('users.statusActive'), value: 1 },
  { label: t('users.statusPending'), value: -1 },
  { label: t('users.statusDisabled'), value: 0 },
  { label: t('users.statusRejected'), value: -2 },
])

const session = useSessionStore()

//: 每页数量选项：默认 15 位用户，页码器上可切换。
const PAGE_SIZE_OPTIONS = [15, 30, 60, 90]

const keyword = ref('')
const statusFilter = ref('')
const users = ref([])
const counts = ref({ total: 0, pending: 0 })
const page = ref(1)
const pageSize = ref(15)
const total = ref(0)
const loading = ref(false)

const pendingHint = computed(() => counts.value.pending > 0 && counts.value.pending)

function metaOf(status) {
  return STATUS_META.value[String(status)] || { label: t('common.unknown'), type: 'info' }
}

function isSelf(user) {
  return user.id === session.user?.id
}

//: 请求序号：快速翻页或改每页数量时，后发的请求可能先回来，旧响应要丢弃。
let requestSeq = 0

async function loadUsers(target = page.value) {
  const seq = ++requestSeq
  loading.value = true
  try {
    const data = await api.get('/users', {
      query: {
        keyword: keyword.value,
        status: statusFilter.value,
        page: target,
        page_size: pageSize.value,
      },
    })
    if (seq !== requestSeq) return
    users.value = data?.items || []
    total.value = Number(data?.total || 0)
    page.value = Number(data?.page || target)
    counts.value = data?.counts || counts.value
  } catch (error) {
    if (seq !== requestSeq) return
    ElMessage.error(errorMessage(error, t('users.loadFailed')))
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

//: 重拉当前页；删空后自动退回上一页，避免停在空白页上。
async function reload() {
  await loadUsers(page.value)
  if (!users.value.length && page.value > 1) await loadUsers(page.value - 1)
}

function changePage(target) {
  loadUsers(target)
}

//: 每页数量变了，原先的页码没有意义，统一回到第 1 页。
function changeSize(size) {
  pageSize.value = Number(size) || pageSize.value
  loadUsers(1)
}

async function refreshCounts() {
  try {
    const data = await api.get('/users', { query: { limit: 1 } })
    counts.value = data?.counts || counts.value
  } catch (error) {
    //: 计数只是辅助信息，刷新失败不打扰用户。
  }
}

async function patch(user, payload, message) {
  try {
    const data = await api.patch(`/users/${user.id}`, { json: payload })
    Object.assign(user, data?.user || {})
    //: 审核/禁用会改变待审核数量，就地刷新角标，不重置当前列表位置。
    if ('status' in payload) refreshCounts()
    ElMessage.success(message)
  } catch (error) {
    ElMessage.error(errorMessage(error, t('users.actionFailed')))
  }
}

function enable(user) {
  patch(user, { status: 1 }, t('users.enabled'))
}

function approve(user) {
  patch(user, { status: 1 }, t('users.approved'))
}

//: 拒绝理由会写进通知邮件，所以先收集再提交，而不是一键拒绝。
const rejectDialog = ref(false)
const rejectReason = ref('')
const rejecting = ref(null)

function reject(user) {
  rejecting.value = user
  rejectReason.value = ''
  rejectDialog.value = true
}

async function confirmReject() {
  if (!rejecting.value) return
  await patch(
    rejecting.value,
    { status: -2, reason: rejectReason.value.trim() },
    t('users.rejectedMsg'),
  )
  rejectDialog.value = false
}

function disable(user) {
  patch(user, { status: 0 }, t('users.disabled'))
}

function grantAdmin(user) {
  patch(user, { is_admin: true }, t('users.adminGranted'))
}

async function revokeAdmin(user) {
  try {
    await ElMessageBox.confirm(
      t('users.adminRevokeConfirm', { name: user.nickname || user.username }),
      t('users.adminRevokeTitle'),
      { type: 'warning' },
    )
  } catch (error) {
    return
  }
  patch(user, { is_admin: false }, t('users.adminRevoked'))
}

async function remove(user) {
  try {
    await ElMessageBox.confirm(
      t('users.deleteConfirm', { name: user.nickname || user.username }),
      t('users.deleteTitle'),
      { type: 'warning', confirmButtonText: t('common.delete') },
    )
  } catch (error) {
    return
  }
  try {
    await api.del(`/users/${user.id}`)
    await reload()
    ElMessage.success(t('users.deleted'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('users.deleteFailed')))
  }
}

function search() {
  return loadUsers(1)
}

onMounted(() => loadUsers(1))
</script>

<template>
  <div class="page">
    <div class="page__header">
      <h2 class="page__title">{{ t('users.title') }}</h2>
      <el-button @click="reload">{{ t('common.refresh') }}</el-button>
    </div>

    <el-card>
      <template #header>
        <div class="card-header">
          <span>
            {{ t('users.totalUsers', { n: counts.total }) }}
            <el-tag v-if="pendingHint" type="warning" size="small" effect="plain">
              {{ t('users.pendingHint', { n: pendingHint }) }}
            </el-tag>
          </span>
          <div class="user-toolbar">
            <el-select
              v-model="statusFilter"
              size="small"
              style="width: 120px"
              @change="search"
            >
              <el-option
                v-for="option in STATUS_FILTERS"
                :key="String(option.value)"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
            <el-input
              v-model="keyword"
              size="small"
              clearable
              :placeholder="t('users.searchPlaceholder')"
              style="width: 200px"
              @keyup.enter="search"
              @clear="search"
            />
            <el-button size="small" type="primary" @click="search">{{ t('common.search') }}</el-button>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="users" size="small">
        <el-table-column :label="t('users.columnUser')" min-width="230">
          <template #default="{ row }">
            <div class="user-cell">
              <span class="user-cell__name" :title="row.username">{{ row.username }}</span>
              <span class="user-cell__count" :title="t('users.imageCountTitle', { n: row.image_count || 0 })">
                {{ row.image_count || 0 }}
              </span>
              <span v-if="row.nickname && row.nickname !== row.username" class="user-cell__nick">
                {{ row.nickname }}
              </span>
              <el-tag v-if="isSelf(row)" size="small" effect="plain">{{ t('users.me') }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="email" :label="t('users.columnEmail')" min-width="170">
          <template #default="{ row }">{{ row.email || '-' }}</template>
        </el-table-column>
        <el-table-column :label="t('users.columnStatus')" width="96">
          <template #default="{ row }">
            <div class="user-status">
              <el-tag size="small" :type="metaOf(row.status).type">
                {{ metaOf(row.status).label }}
              </el-tag>
              <span
                v-if="row.status === -2 && row.status_reason"
                class="user-cell__nick"
                :title="row.status_reason"
              >
                {{ row.status_reason }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('users.columnRole')" width="88">
          <template #default="{ row }">
            <el-tag v-if="row.is_admin" size="small" type="danger" effect="plain">
              {{ t('users.roleAdmin') }}
            </el-tag>
            <span v-else class="user-cell__nick">{{ t('users.roleUser') }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('users.columnRegisteredAt')" width="162">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column :label="t('users.columnActions')" width="200" align="left">
          <template #default="{ row }">
            <template v-if="!isSelf(row)">
              <template v-if="row.status === -1">
                <el-button link type="success" size="small" @click="approve(row)">
                  {{ t('users.approve') }}
                </el-button>
                <el-button link type="danger" size="small" @click="reject(row)">
                  {{ t('users.reject') }}
                </el-button>
              </template>
              <el-button
                v-else-if="row.status === 1"
                link
                type="warning"
                size="small"
                @click="disable(row)"
              >
                {{ t('users.disable') }}
              </el-button>
              <el-button v-else link type="success" size="small" @click="enable(row)">
                {{ t('users.enable') }}
              </el-button>

              <el-button
                v-if="!row.is_admin"
                link
                type="primary"
                size="small"
                @click="grantAdmin(row)"
              >
                {{ t('users.grantAdmin') }}
              </el-button>
              <el-button v-else link type="danger" size="small" @click="revokeAdmin(row)">
                {{ t('users.revokeAdmin') }}
              </el-button>
              <el-button link type="danger" size="small" @click="remove(row)">
                {{ t('common.delete') }}
              </el-button>
            </template>
            <span v-else class="user-cell__nick">{{ t('users.currentAccount') }}</span>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :description="t('users.empty')" :image-size="60" />
        </template>
      </el-table>

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
      </div>
    </el-card>

    <el-dialog v-model="rejectDialog" :title="t('users.rejectTitle')" width="440px">
      <el-form label-position="top">
        <el-form-item :label="t('users.rejectReason')">
          <el-input
            v-model="rejectReason"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            :placeholder="t('users.rejectReasonPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <p class="hint">
        {{ t('users.rejectHint') }}
      </p>
      <template #footer>
        <el-button @click="rejectDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="danger" @click="confirmReject">{{ t('users.confirmReject') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>
