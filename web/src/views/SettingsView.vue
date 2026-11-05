<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, errorMessage } from '@/api/client'
import AvatarCropper from '@/components/AvatarCropper.vue'
import HookSlot from '@/components/hook/HookSlot.vue'
import { useSessionStore } from '@/stores/session'
import { useSiteStore } from '@/stores/site'
import { formatTime } from '@/utils/format'

const EXPIRES = [
  { label: '永久', value: 0 },
  { label: '30 天', value: 30 },
  { label: '90 天', value: 90 },
  { label: '365 天', value: 365 },
]

//: 与后端 libs.auth 的 PAT_SCOPES 一一对应；admin 仅在管理员勾选时出现。
const DEFAULT_SCOPES = ['read', 'upload', 'write']
const SCOPES = [
  { label: '读取（GET 接口）', value: 'read' },
  { label: '上传图片', value: 'upload' },
  { label: '写入（修改/删除相册与图片）', value: 'write' },
  { label: '管理后台', value: 'admin', admin: true },
]

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const site = useSiteStore()

//: 账号设置分区块展示，左栏切换；区块 key 同时写进 ?tab= 便于刷新与分享。
const SECTIONS = [
  { key: 'profile', label: '账号信息', icon: 'UserFilled' },
  { key: 'password', label: '修改密码', icon: 'Key' },
  { key: 'tokens', label: '访问令牌', icon: 'Connection' },
  { key: 'identities', label: '统一登录', icon: 'Link' },
]
const SECTION_KEYS = SECTIONS.map((section) => section.key)

function sectionFromQuery() {
  const value = Array.isArray(route.query.tab) ? route.query.tab[0] : route.query.tab
  return SECTION_KEYS.includes(value) ? value : 'profile'
}

const activeSection = ref(sectionFromQuery())

function switchSection(key) {
  if (activeSection.value === key) return
  activeSection.value = key
  router.replace({ query: { ...route.query, tab: key } })
}

watch(
  () => route.query.tab,
  (value) => {
    const next = SECTION_KEYS.includes(value) ? value : 'profile'
    if (next !== activeSection.value) activeSection.value = next
  },
)

const identities = ref([])

const profile = reactive({ nickname: '', email: '', avatar: '' })
const savingProfile = ref(false)
const cropperVisible = ref(false)
const sendingVerify = ref(false)
const confirming = ref(false)
//: 邮件寄出后才有必要让人填令牌，所以单独控制这一行的显隐。
const verifySent = ref(false)
const verifyToken = ref('')

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
const tokenForm = reactive({ name: '', expires_in: 0, scopes: [...DEFAULT_SCOPES] })

//: 改了地址就作废上一轮验证，避免把旧令牌贴到新邮箱上。
watch(
  () => profile.email,
  () => {
    verifySent.value = false
    verifyToken.value = ''
  },
)

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

//: 只有验证通过的邮箱才算「绑定」，未验证地址既不能找回密码也不能关联统一登录。
async function submitVerifyToken(token) {
  if (!token) {
    ElMessage.warning('请填写邮件中的令牌')
    return
  }
  confirming.value = true
  try {
    const data = await api.post('/auth/email/confirm', { json: { token } })
    session.updateUser(data?.user)
    verifySent.value = false
    verifyToken.value = ''
    ElMessage.success('邮箱已验证')
  } catch (error) {
    ElMessage.error(errorMessage(error, '邮箱验证失败'))
  } finally {
    confirming.value = false
  }
}

async function verifyEmail() {
  if (!session.user?.email) {
    ElMessage.warning('请先填写邮箱并保存')
    return
  }
  if (profile.email !== session.user.email) {
    ElMessage.warning('邮箱有未保存的改动，请先保存')
    return
  }
  if (!site.mailEnabled) {
    ElMessage.warning('站点未配置邮件服务，请联系管理员')
    return
  }
  sendingVerify.value = true
  try {
    const sent = await api.post('/auth/email/verify')
    const token = sent?.verify_token || ''
    //: 本地/测试环境没有邮件服务，后端会直接把令牌回传。
    if (token) {
      await submitVerifyToken(token)
      return
    }
    verifySent.value = true
    ElMessage.success('验证邮件已发送，请查收邮件并提交令牌')
  } catch (error) {
    ElMessage.error(
      error?.code === 'SERVICE_UNAVAILABLE'
        ? '站点未配置邮件服务，请联系管理员'
        : errorMessage(error, '邮箱验证失败'),
    )
  } finally {
    sendingVerify.value = false
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
  Object.assign(tokenForm, {
    name: '',
    expires_in: 0,
    scopes: [...DEFAULT_SCOPES],
  })
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
        scopes: tokenForm.scopes,
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

async function loadIdentities() {
  try {
    const data = await api.get('/auth/identities')
    identities.value = data?.items || []
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载登录方式失败'))
  }
}

function bindIdentity(item) {
  window.location.href = item.bind_url
}

async function unbindIdentity(item) {
  let password = ''
  try {
    const { value } = await ElMessageBox.prompt(
      '解除后该账号无法再通过统一登录进入，请输入当前密码确认',
      '解除绑定',
      {
        inputType: 'password',
        inputValidator: (value) => Boolean(value) || '请输入密码',
      }
    )
    password = value
  } catch (error) {
    return
  }
  try {
    await api.del(`/auth/identities/${item.name}`, { json: { password } })
    ElMessage.success('已解除绑定')
    await loadIdentities()
  } catch (error) {
    ElMessage.error(errorMessage(error, '解除绑定失败'))
  }
}

onMounted(() => {
  syncProfile()
  loadTokens()
  loadIdentities()
  const flag = typeof route.query.identity === 'string' ? route.query.identity : ''
  if (flag === 'bound') ElMessage.success('统一登录已绑定')
  if (flag === 'error') ElMessage.error('绑定失败，该身份可能已绑定到其他账号')
  //: 绑定回跳直接落在「统一登录」区块，省得用户自己找。
  if (flag) switchSection('identities')
})
</script>

<template>
  <div class="page side-shell">
    <aside class="side-nav">
      <div class="side-nav__title">账号设置</div>
      <nav class="side-nav__menu">
        <button
          v-for="section in SECTIONS"
          :key="section.key"
          type="button"
          class="side-nav__link"
          :class="{ 'is-active': activeSection === section.key }"
          @click="switchSection(section.key)"
        >
          <el-icon><component :is="section.icon" /></el-icon>
          <span>{{ section.label }}</span>
        </button>
      </nav>
    </aside>

    <section class="side-main">
      <el-card v-if="activeSection === 'profile'">
        <template #header>账号信息</template>
        <el-form class="side-main__form" label-position="top">
          <el-form-item label="用户名">
            <el-input :model-value="session.user?.username || ''" disabled />
          </el-form-item>
          <el-form-item label="昵称">
            <el-input v-model="profile.nickname" maxlength="64" placeholder="右上角显示的名称" />
          </el-form-item>
          <el-form-item label="邮箱">
            <el-input v-model="profile.email" placeholder="用于找回密码与统一登录关联，可留空" />
            <div v-if="session.user?.email" class="email-verify">
              <el-tag
                size="small"
                :type="session.user?.email_verified ? 'success' : 'warning'"
                effect="plain"
              >
                {{ session.user?.email_verified ? '已验证' : '未验证' }}
              </el-tag>
              <el-button
                v-if="!session.user?.email_verified"
                size="small"
                link
                type="primary"
                :loading="sendingVerify"
                :disabled="!site.mailEnabled"
                @click="verifyEmail"
              >
                发送验证邮件
              </el-button>
              <el-input
                v-if="verifySent && !session.user?.email_verified"
                v-model="verifyToken"
                class="email-verify__token"
                size="small"
                placeholder="粘贴邮件中的令牌"
              >
                <template #append>
                  <el-button :loading="confirming" @click="submitVerifyToken(verifyToken)">
                    验证
                  </el-button>
                </template>
              </el-input>
              <span class="node-field__help">
                {{
                  site.mailEnabled
                    ? '验证后才能用该邮箱找回密码、关联统一登录'
                    : '站点未配置邮件服务，暂时无法验证邮箱'
                }}
              </span>
            </div>
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

      <el-card v-else-if="activeSection === 'password'">
        <template #header>修改密码</template>
        <el-form class="side-main__form" label-position="top">
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

      <el-card v-else-if="activeSection === 'tokens'">
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
          <el-table-column label="权限" min-width="140">
            <template #default="{ row }">
              <el-tag
                v-for="scope in row.scopes || []"
                :key="scope"
                size="small"
                effect="plain"
                style="margin-right: 4px"
              >
                {{ scope }}
              </el-tag>
            </template>
          </el-table-column>
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

      <el-card v-else>
        <template #header>统一登录</template>
        <p class="hint">
          绑定后可用对应的平台账号登录本站；解除绑定需要输入当前密码。关闭「密码登录」后，
          这里将是唯一的登录方式。
        </p>
        <div
          v-for="item in identities"
          :key="item.name"
          style="
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 8px 0;
            border-bottom: 1px solid var(--el-border-color-lighter);
          "
        >
          <span style="flex: 1">{{ item.title }}</span>
          <el-tag size="small" :type="item.bound ? 'success' : 'info'">
            {{ item.bound ? '已绑定' : '未绑定' }}
          </el-tag>
          <el-button
            v-if="item.bound"
            link
            type="danger"
            @click="unbindIdentity(item)"
          >
            解除绑定
          </el-button>
          <el-button v-else link type="primary" @click="bindIdentity(item)">
            立即绑定
          </el-button>
        </div>
        <el-empty
          v-if="!identities.length"
          description="站点未启用第三方登录"
          :image-size="60"
        />
      </el-card>

      <HookSlot
        slot="user.setting"
        :context="{ user: session.user }"
        show-title
        style="margin-top: 16px"
      />
    </section>

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
        <el-form-item label="权限范围">
          <el-checkbox-group v-model="tokenForm.scopes">
            <el-checkbox
              v-for="option in SCOPES"
              v-show="!option.admin || session.user?.is_admin"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </el-checkbox>
          </el-checkbox-group>
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
