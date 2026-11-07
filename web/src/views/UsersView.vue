<script setup>
import { computed, onMounted, ref } from 'vue'

import { api, errorMessage } from '@/api/client'
import { useSessionStore } from '@/stores/session'
import { formatTime } from '@/utils/format'

const STATUS_META = {
  '-2': { label: '已拒绝', type: 'info' },
  '-1': { label: '待审核', type: 'warning' },
  0: { label: '已禁用', type: 'danger' },
  1: { label: '正常', type: 'success' },
}

const STATUS_FILTERS = [
  { label: '全部状态', value: '' },
  { label: '正常', value: 1 },
  { label: '待审核', value: -1 },
  { label: '已禁用', value: 0 },
  { label: '已拒绝', value: -2 },
]

const session = useSessionStore()

const keyword = ref('')
const statusFilter = ref('')
const users = ref([])
const counts = ref({ total: 0, pending: 0 })
const cursor = ref(null)
const hasMore = ref(false)
const loading = ref(false)

const pendingHint = computed(() => counts.value.pending > 0 && counts.value.pending)

function metaOf(status) {
  return STATUS_META[String(status)] || { label: '未知', type: 'info' }
}

function isSelf(user) {
  return user.id === session.user?.id
}

async function loadUsers(reset = false) {
  loading.value = true
  try {
    const data = await api.get('/users', {
      query: {
        keyword: keyword.value,
        status: statusFilter.value,
        cursor: reset ? '' : cursor.value,
        limit: 20,
      },
    })
    users.value = reset ? data?.items || [] : users.value.concat(data?.items || [])
    counts.value = data?.counts || counts.value
    cursor.value = data?.next_cursor || null
    hasMore.value = Boolean(data?.has_more)
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载用户失败'))
  } finally {
    loading.value = false
  }
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
    ElMessage.error(errorMessage(error, '操作失败'))
  }
}

function enable(user) {
  patch(user, { status: 1 }, '账号已启用')
}

function approve(user) {
  patch(user, { status: 1 }, '已通过审核')
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
    '已拒绝该注册申请',
  )
  rejectDialog.value = false
}

function disable(user) {
  patch(user, { status: 0 }, '账号已禁用')
}

function grantAdmin(user) {
  patch(user, { is_admin: true }, '已设为管理员')
}

async function revokeAdmin(user) {
  try {
    await ElMessageBox.confirm(
      `确定取消「${user.nickname || user.username}」的管理员权限吗？`,
      '取消管理员',
      { type: 'warning' },
    )
  } catch (error) {
    return
  }
  patch(user, { is_admin: false }, '已取消管理员权限')
}

async function remove(user) {
  try {
    await ElMessageBox.confirm(
      `删除「${user.nickname || user.username}」会同时删除其相册、图片与令牌，且无法恢复。确定继续吗？`,
      '删除用户',
      { type: 'warning', confirmButtonText: '删除' },
    )
  } catch (error) {
    return
  }
  try {
    await api.del(`/users/${user.id}`)
    users.value = users.value.filter((item) => item.id !== user.id)
    refreshCounts()
    ElMessage.success('用户已删除')
  } catch (error) {
    ElMessage.error(errorMessage(error, '删除失败'))
  }
}

function search() {
  loadUsers(true)
}

onMounted(() => loadUsers(true))
</script>

<template>
  <div class="page">
    <div class="page__header">
      <h2 class="page__title">用户管理</h2>
      <el-button @click="loadUsers(true)">刷新</el-button>
    </div>

    <el-card>
      <template #header>
        <div class="card-header">
          <span>
            共 {{ counts.total }} 位用户
            <el-tag v-if="pendingHint" type="warning" size="small" effect="plain">
              {{ pendingHint }} 待审核
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
              placeholder="用户名 / 昵称 / 邮箱"
              style="width: 200px"
              @keyup.enter="search"
              @clear="search"
            />
            <el-button size="small" type="primary" @click="search">搜索</el-button>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="users" size="small">
        <el-table-column label="用户" min-width="160">
          <template #default="{ row }">
            <div class="user-cell">
              <span class="user-cell__name">{{ row.username }}</span>
              <span v-if="row.nickname && row.nickname !== row.username" class="user-cell__nick">
                {{ row.nickname }}
              </span>
              <el-tag v-if="isSelf(row)" size="small" effect="plain">我</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="180">
          <template #default="{ row }">{{ row.email || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="150">
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
        <el-table-column label="角色" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.is_admin" size="small" type="danger" effect="plain">
              管理员
            </el-tag>
            <span v-else class="user-cell__nick">普通用户</span>
          </template>
        </el-table-column>
        <el-table-column label="注册时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="240" align="right">
          <template #default="{ row }">
            <template v-if="!isSelf(row)">
              <template v-if="row.status === -1">
                <el-button link type="success" size="small" @click="approve(row)">
                  通过
                </el-button>
                <el-button link type="danger" size="small" @click="reject(row)">
                  拒绝
                </el-button>
              </template>
              <el-button
                v-else-if="row.status === 1"
                link
                type="warning"
                size="small"
                @click="disable(row)"
              >
                禁用
              </el-button>
              <el-button v-else link type="success" size="small" @click="enable(row)">
                启用
              </el-button>

              <el-button
                v-if="!row.is_admin"
                link
                type="primary"
                size="small"
                @click="grantAdmin(row)"
              >
                设为管理员
              </el-button>
              <el-button v-else link type="danger" size="small" @click="revokeAdmin(row)">
                取消管理员
              </el-button>
              <el-button link type="danger" size="small" @click="remove(row)">
                删除
              </el-button>
            </template>
            <span v-else class="user-cell__nick">当前账号</span>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="没有匹配的用户" :image-size="60" />
        </template>
      </el-table>

      <div v-if="hasMore" class="load-more">
        <el-button size="small" :loading="loading" @click="loadUsers(false)">
          加载更多
        </el-button>
      </div>
    </el-card>

    <el-dialog v-model="rejectDialog" title="拒绝注册申请" width="440px">
      <el-form label-position="top">
        <el-form-item label="拒绝理由">
          <el-input
            v-model="rejectReason"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            placeholder="会写进通知邮件，可留空"
          />
        </el-form-item>
      </el-form>
      <p class="hint">
        拒绝后账号状态变为「已拒绝」并吊销既有会话；若该用户邮箱已验证，会收到一封含理由的通知邮件。
      </p>
      <template #footer>
        <el-button @click="rejectDialog = false">取消</el-button>
        <el-button type="danger" @click="confirmReject">确认拒绝</el-button>
      </template>
    </el-dialog>
  </div>
</template>
