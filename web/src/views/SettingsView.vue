<script setup>
import { onMounted, reactive, ref } from 'vue'

import { api, errorMessage } from '@/api/client'
import AvatarCropper from '@/components/AvatarCropper.vue'
import HookSlot from '@/components/hook/HookSlot.vue'
import { useSessionStore } from '@/stores/session'
import { formatTime } from '@/utils/format'

const EXPIRES = [
  { label: '永久', value: 0 },
  { label: '30 天', value: 30 },
  { label: '90 天', value: 90 },
  { label: '365 天', value: 365 },
]

const session = useSessionStore()

const profile = reactive({ nickname: '', email: '', avatar: '' })
const savingProfile = ref(false)
const cropperVisible = ref(false)

const avatarInitial = () =>
  (profile.nickname || session.user?.username || '?').slice(0, 1)

function onAvatarUploaded(data) {
  profile.avatar = data?.avatar || ''
  session.updateUser(data?.user)
}

const password = reactive({ old_password: '', new_password: '' })
const changing = ref(false)

const tokens = ref([])
const tokensLoading = ref(false)
const tokenDialog = ref(false)
const tokenSaving = ref(false)
const createdToken = ref(null)
const tokenForm = reactive({ name: '', expires_in: 0 })

function syncProfile() {
  Object.assign(profile, {
    nickname: session.user?.nickname || '',
    email: session.user?.email || '',
    avatar: session.user?.avatar || '',
  })
}

async function saveProfile() {
  savingProfile.value = true
  try {
    const data = await api.put('/auth/profile', { json: { ...profile } })
    session.updateUser(data?.user)
    ElMessage.success('账号信息已更新')
  } catch (error) {
    ElMessage.error(errorMessage(error, '保存失败'))
  } finally {
    savingProfile.value = false
  }
}

async function changePassword() {
  changing.value = true
  try {
    await session.changePassword({ ...password })
    Object.assign(password, { old_password: '', new_password: '' })
    ElMessage.success('密码已更新')
  } catch (error) {
    ElMessage.error(errorMessage(error, '修改密码失败'))
  } finally {
    changing.value = false
  }
}

async function loadTokens() {
  tokensLoading.value = true
  try {
    const data = await api.get('/auth/tokens')
    tokens.value = data?.items || []
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载令牌失败'))
  } finally {
    tokensLoading.value = false
  }
}

function openTokenDialog() {
  Object.assign(tokenForm, { name: '', expires_in: 0 })
  createdToken.value = null
  tokenDialog.value = true
}

async function createToken() {
  tokenSaving.value = true
  try {
    const expiresIn = Number(tokenForm.expires_in || 0) * 24 * 3600
    const data = await api.post('/auth/tokens', {
      json: {
        name: tokenForm.name,
        expires_in: expiresIn || undefined,
      },
    })
    createdToken.value = data?.token || null
    await loadTokens()
  } catch (error) {
    ElMessage.error(errorMessage(error, '创建令牌失败'))
  } finally {
    tokenSaving.value = false
  }
}

async function revoke(row) {
  try {
    await ElMessageBox.confirm(`确定撤销「${row.name || row.prefix}」吗？`, '撤销令牌', {
      type: 'warning',
    })
  } catch (error) {
    return
  }
  try {
    await api.del(`/auth/tokens/${row.id}`)
    ElMessage.success('已撤销')
    await loadTokens()
  } catch (error) {
    ElMessage.error(errorMessage(error, '撤销失败'))
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

onMounted(() => {
  syncProfile()
  loadTokens()
})
</script>

<template>
  <div class="page">
    <div class="page__header">
      <h2 class="page__title">账号设置</h2>
    </div>

    <el-row :gutter="16">
      <el-col :xs="24" :md="12">
        <el-card>
          <template #header>账号信息</template>
          <el-form label-position="top">
            <el-form-item label="用户名">
              <el-input :model-value="session.user?.username || ''" disabled />
            </el-form-item>
            <el-form-item label="昵称">
              <el-input v-model="profile.nickname" maxlength="64" placeholder="右上角显示的名称" />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="profile.email" placeholder="用于找回密码，可留空" />
            </el-form-item>
            <el-form-item label="头像">
              <div class="avatar-field">
                <el-avatar :size="56" :src="profile.avatar || undefined">
                  {{ avatarInitial() }}
                </el-avatar>
                <el-button size="small" @click="cropperVisible = true">
                  上传头像
                </el-button>
                <el-button
                  v-if="profile.avatar"
                  size="small"
                  text
                  @click="profile.avatar = ''"
                >
                  清除
                </el-button>
              </div>
              <div class="node-field__help">
                上传后拖动、缩放裁剪，保存的图片会存入你的默认相册
              </div>
            </el-form-item>
            <div class="form-actions">
              <el-button type="primary" :loading="savingProfile" @click="saveProfile">
                保存
              </el-button>
              <span class="form-actions__meta">
                {{ session.isAdmin ? '管理员' : '普通用户' }} ·
                {{ formatTime(session.user?.created_at) }} 注册
              </span>
            </div>
          </el-form>
          <HookSlot
            slot="profile"
            :context="{ user: session.user }"
            style="margin-top: 12px"
          />
        </el-card>
      </el-col>

      <el-col :xs="24" :md="12">
        <el-card>
          <template #header>修改密码</template>
          <el-form label-position="top">
            <el-form-item label="当前密码">
              <el-input v-model="password.old_password" type="password" show-password />
            </el-form-item>
            <el-form-item label="新密码">
              <el-input v-model="password.new_password" type="password" show-password />
            </el-form-item>
            <el-button type="primary" :loading="changing" @click="changePassword">
              更新密码
            </el-button>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <el-card style="margin-top: 16px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>访问令牌（PAT）</span>
          <el-button size="small" type="primary" @click="openTokenDialog">
            新建令牌
          </el-button>
        </div>
      </template>
      <p class="hint">
        访问令牌（Personal Access Token）用于 PicGo、uPic、CLI 等客户端代替密码调用上传
        API：请求头携带 <code>Authorization: Bearer &lt;令牌&gt;</code>，令牌只在创建时显示一次，
        可随时撤销。
      </p>
      <el-table v-loading="tokensLoading" :data="tokens" size="small">
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column prop="prefix" label="前缀" width="140" />
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="最近使用" width="180">
          <template #default="{ row }">{{ formatTime(row.last_used_at) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.revoked ? 'info' : 'success'">
              {{ row.revoked ? '已撤销' : '有效' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="right">
          <template #default="{ row }">
            <el-button
              link
              type="danger"
              :disabled="row.revoked"
              @click="revoke(row)"
            >
              撤销
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="还没有令牌" :image-size="60" />
        </template>
      </el-table>
    </el-card>

    <HookSlot
      slot="user.setting"
      :context="{ user: session.user }"
      show-title
      style="margin-top: 16px"
    />

    <AvatarCropper v-model="cropperVisible" @uploaded="onAvatarUploaded" />

    <el-dialog v-model="tokenDialog" title="新建令牌" width="440px">
      <el-form label-position="top">
        <el-form-item label="名称">
          <el-input v-model="tokenForm.name" maxlength="64" placeholder="如 picgo" />
        </el-form-item>
        <el-form-item label="有效期">
          <el-select v-model="tokenForm.expires_in" style="width: 100%">
            <el-option
              v-for="option in EXPIRES"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="createdToken"
        type="success"
        :closable="false"
        show-icon
        title="令牌只显示一次，请立即保存"
      >
        <div style="display: flex; align-items: center; gap: 8px; margin-top: 8px">
          <code style="word-break: break-all">{{ createdToken }}</code>
          <el-button link type="primary" @click="copy(createdToken)">复制</el-button>
        </div>
      </el-alert>

      <template #footer>
        <el-button @click="tokenDialog = false">关闭</el-button>
        <el-button
          v-if="!createdToken"
          type="primary"
          :loading="tokenSaving"
          @click="createToken"
        >
          创建
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
