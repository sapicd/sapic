<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, errorMessage } from '@/api/client'
import AvatarCropper from '@/components/AvatarCropper.vue'
import HookSlot from '@/components/hook/HookSlot.vue'
import { hookText } from '@/components/hook/text'
import { locale, t } from '@/i18n'
import { useSessionStore } from '@/stores/session'
import { useSiteStore } from '@/stores/site'
import { albumName } from '@/utils/album'
import { formatShortTime, formatTime } from '@/utils/format'

const EXPIRES = computed(() => [
  { label: t('upload.forever'), value: 0 },
  { label: t('upload.days', { n: 30 }), value: 30 },
  { label: t('upload.days', { n: 90 }), value: 90 },
  { label: t('upload.days', { n: 365 }), value: 365 },
])

//: 与后端 libs.auth 的 PAT_SCOPES 一一对应；admin 仅在管理员勾选时出现。
const DEFAULT_SCOPES = ['read', 'upload', 'write']
const SCOPES = computed(() => [
  { label: t('settings.scopeRead'), value: 'read' },
  { label: t('settings.scopeUpload'), value: 'upload' },
  { label: t('settings.scopeWrite'), value: 'write' },
  { label: t('settings.scopeAdmin'), value: 'admin', admin: true },
])

//: Swagger 文档挂在后端 `/api/v2` 下：dev 由 vite 代理，生产同源，直接用绝对路径即可。
//: 文档有中英两版，链接跟着界面语言走（`?lang=zh|en`），否则英文界面会打开中文文档。
const API_DOCS_URL = computed(() => `/api/v2/docs?lang=${locale.value}`)

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const site = useSiteStore()

//: 账号设置分区块展示，左栏切换；区块 key 同时写进 ?tab= 便于刷新与分享。
const SECTIONS = computed(() => [
  { key: 'profile', label: t('settings.secProfile'), icon: 'UserFilled' },
  { key: 'preferences', label: t('settings.secPreferences'), icon: 'Brush' },
  { key: 'password', label: t('settings.secPassword'), icon: 'Key' },
  { key: 'tokens', label: t('settings.secTokens'), icon: 'Connection' },
  { key: 'identities', label: t('settings.secIdentities'), icon: 'Link' },
])
const SECTION_KEYS = ['profile', 'preferences', 'password', 'tokens', 'identities']

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

//: 自助注销：后端要求当前密码 + 名下无图片，管理员需由其他管理员删除。
const deleteDialog = ref(false)
const deletePassword = ref('')
const deleting = ref(false)

function openDeleteAccount() {
  deletePassword.value = ''
  deleteDialog.value = true
}

async function confirmDeleteAccount() {
  if (!deletePassword.value) {
    ElMessage.warning(t('settings.currentPasswordRequired'))
    return
  }
  deleting.value = true
  try {
    await session.deleteAccount(deletePassword.value)
    deleteDialog.value = false
    ElMessage.success(t('settings.accountDeleted'))
    router.push({ name: 'home' })
  } catch (error) {
    ElMessage.error(errorMessage(error, t('settings.deleteAccountFailed')))
  } finally {
    deleting.value = false
  }
}

//: 个性化设置（/auth/settings）：油猴脚本开关、个人背景图与防盗链。
const prefs = reactive({
  userscript_enabled: false,
  bg_image: '',
  bg_image_mobile: '',
  bg_opacity: null,
  hotlink_enabled: false,
  hotlink_allow_hosts: '',
  hotlink_allow_empty: true,
})
const savingPrefs = ref(false)

//: 滑块只能绑数值：null 表示跟随站点，展示时用站点值兜底，拖动即写入个人值。
const opacityValue = computed({
  get: () => prefs.bg_opacity ?? site.backgroundOpacity,
  set: (value) => {
    prefs.bg_opacity = value
  },
})

//: 恢复「跟随站点」：清掉个人值而不是写入当前站点值，否则站点改遮罩时这里不会再跟。
function followSiteOpacity() {
  prefs.bg_opacity = null
}

//: 脚本随开关实时失效，安装/更新链接用当前站点根地址拼出来即可。
//: 路径在 /api/v2 下，所以不需要额外的前端路由或反向代理规则。
const userscriptUrl = computed(
  () => new URL('/api/v2/userscript.user.js', window.location.origin).toString(),
)

function syncPrefs() {
  const saved = session.settings || {}
  prefs.userscript_enabled = saved.userscript_enabled ?? false
  prefs.bg_image = saved.bg_image || ''
  prefs.bg_image_mobile = saved.bg_image_mobile || ''
  prefs.bg_opacity = saved.bg_opacity ?? null
  prefs.hotlink_enabled = saved.hotlink_enabled ?? false
  prefs.hotlink_allow_hosts = saved.hotlink_allow_hosts || ''
  prefs.hotlink_allow_empty = saved.hotlink_allow_empty ?? true
}

async function savePrefs() {
  savingPrefs.value = true
  try {
    await session.saveSettings({ ...prefs })
    ElMessage.success(t('settings.prefsSaved'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('albums.saveFailed')))
  } finally {
    savingPrefs.value = false
  }
}

const tokens = ref([])
const tokensLoading = ref(false)
const tokenDialog = ref(false)
const tokenSaving = ref(false)
const createdToken = ref(null)
//: 可选「默认相册」：只有自己的相册和被授予可写的共享相册能作为上传目标。
const tokenAlbums = ref([])
const tokenForm = reactive({
  name: '',
  expires_in: 0,
  scopes: [...DEFAULT_SCOPES],
  album_id: null,
})

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
    ElMessage.success(t('settings.profileUpdated'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('albums.saveFailed')))
  } finally {
    savingProfile.value = false
  }
}

//: 只有验证通过的邮箱才算「绑定」，未验证地址既不能找回密码也不能关联统一登录。
async function submitVerifyToken(token) {
  if (!token) {
    ElMessage.warning(t('settings.tokenRequired'))
    return
  }
  confirming.value = true
  try {
    const data = await api.post('/auth/email/confirm', { json: { token } })
    session.updateUser(data?.user)
    verifySent.value = false
    verifyToken.value = ''
    ElMessage.success(t('settings.emailVerified'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('settings.emailVerifyFailed')))
  } finally {
    confirming.value = false
  }
}

async function verifyEmail() {
  if (!session.user?.email) {
    ElMessage.warning(t('settings.emailNeeded'))
    return
  }
  if (profile.email !== session.user.email) {
    ElMessage.warning(t('settings.emailUnsaved'))
    return
  }
  if (!site.mailEnabled) {
    ElMessage.warning(t('settings.mailNotConfigured'))
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
    ElMessage.success(t('settings.verifyMailSent'))
  } catch (error) {
    ElMessage.error(
      error?.code === 'SERVICE_UNAVAILABLE'
        ? t('settings.mailNotConfigured')
        : errorMessage(error, t('settings.emailVerifyFailed')),
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
    ElMessage.success(t('settings.passwordUpdated'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('settings.passwordFailed')))
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
    ElMessage.error(errorMessage(error, t('settings.tokensLoadFailed')))
  } finally {
    tokensLoading.value = false
  }
}

async function loadTokenAlbums() {
  try {
    const data = await api.get('/albums')
    tokenAlbums.value = (data?.items || []).filter(
      (album) => album.role === 'owner' || album.permission === 'write',
    )
  } catch (error) {
    //: 相册列表只是「默认相册」下拉的候选，取不到就不提供该选项。
    tokenAlbums.value = []
  }
}

function openTokenDialog() {
  Object.assign(tokenForm, {
    name: '',
    expires_in: 0,
    scopes: [...DEFAULT_SCOPES],
    album_id: null,
  })
  createdToken.value = null
  tokenDialog.value = true
  if (!tokenAlbums.value.length) loadTokenAlbums()
}

async function createToken() {
  //: 后端不再把空列表当默认权限，空选直接拦在前端。
  if (!tokenForm.scopes.length) {
    ElMessage.warning(t('settings.scopeRequired'))
    return
  }
  tokenSaving.value = true
  try {
    const expiresIn = Number(tokenForm.expires_in || 0) * 24 * 3600
    const data = await api.post('/auth/tokens', {
      json: {
        name: tokenForm.name,
        expires_in: expiresIn || undefined,
        scopes: tokenForm.scopes,
        album_id: tokenForm.album_id || undefined,
      },
    })
    createdToken.value = data?.token || null
    await loadTokens()
  } catch (error) {
    ElMessage.error(errorMessage(error, t('settings.tokenCreateFailed')))
  } finally {
    tokenSaving.value = false
  }
}

async function revoke(row) {
  try {
    await ElMessageBox.confirm(t('settings.tokenRevokeConfirm', { name: row.name || row.prefix }), t('settings.tokenRevokeTitle'), {
      type: 'warning',
    })
  } catch (error) {
    return
  }
  try {
    await api.del(`/auth/tokens/${row.id}`)
    ElMessage.success(t('settings.revoked'))
    await loadTokens()
  } catch (error) {
    ElMessage.error(errorMessage(error, t('settings.tokenRevokeFailed')))
  }
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success(t('common.copiedToast'))
  } catch (error) {
    ElMessage.warning(t('common.copyFailed'))
  }
}

async function loadIdentities() {
  try {
    const data = await api.get('/auth/identities')
    identities.value = data?.items || []
  } catch (error) {
    ElMessage.error(errorMessage(error, t('settings.identitiesLoadFailed')))
  }
}

//: 钩子自带 i18n 键时优先用它翻译名称，其次按模块名兜底，最后回落到后端给的 title。
function identityTitle(item) {
  return hookText(item.name, 'title', item.title, item.title_key)
}

//: 已绑定的第三方账号：优先显示人能认出来的信息；都没有时才露出 provider
//: 地址与 UID（老绑定可能既没有昵称也没有邮箱）。
function identityMeta(item) {
  if (!item?.bound) return []
  const parts = []
  if (item.display_name) parts.push({ key: 'name', text: item.display_name })
  if (item.email) parts.push({ key: 'email', text: item.email })
  if (!parts.length) {
    if (item.issuer) parts.push({ key: 'issuer', text: item.issuer })
    if (item.subject) {
      parts.push({ key: 'uid', text: t('settings.linkedUid', { uid: item.subject }) })
    }
  }
  return parts
}

function bindIdentity(item) {
  window.location.href = item.bind_url
}

async function unbindIdentity(item) {
  if (!session.user?.password_set) {
    //: 解绑要提交当前密码；统一登录建号的账号还没有可用的本地密码，先去设一个。
    ElMessage.warning(t('settings.unbindNeedPassword'))
    switchSection('password')
    return
  }
  let password = ''
  try {
    const { value } = await ElMessageBox.prompt(
      t('settings.unbindPrompt'),
      t('settings.unbindTitle'),
      {
        inputType: 'password',
        inputValidator: (value) => Boolean(value) || t('settings.passwordPrompt'),
      }
    )
    password = value
  } catch (error) {
    return
  }
  try {
    await api.del(`/auth/identities/${item.name}`, { json: { password } })
    ElMessage.success(t('settings.unbound'))
    await loadIdentities()
  } catch (error) {
    ElMessage.error(errorMessage(error, t('settings.unbindFailed')))
  }
}

onMounted(() => {
  syncProfile()
  syncPrefs()
  loadTokens()
  loadIdentities()
  const flag = typeof route.query.identity === 'string' ? route.query.identity : ''
  if (flag === 'bound') ElMessage.success(t('settings.bound'))
  if (flag === 'conflict')
    ElMessage.error(t('settings.bindConflict'))
  if (flag === 'error') ElMessage.error(t('settings.bindFailed'))
  //: 绑定回跳直接落在「统一登录」区块，省得用户自己找。
  if (flag) switchSection('identities')
})
</script>

<template>
  <div class="page side-shell">
    <aside class="side-nav">
      <div class="side-nav__title">{{ t('settings.title') }}</div>
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
        <template #header>{{ t('settings.profileHeader') }}</template>
        <el-form class="side-main__form" label-position="top">
          <el-form-item :label="t('settings.username')">
            <el-input :model-value="session.user?.username || ''" disabled />
          </el-form-item>
          <el-form-item :label="t('settings.nickname')">
            <el-input v-model="profile.nickname" maxlength="64" :placeholder="t('settings.nicknamePlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('settings.email')">
            <el-input v-model="profile.email" :placeholder="t('settings.emailPlaceholder')" />
            <div v-if="session.user?.email" class="email-verify">
              <el-tag
                size="small"
                :type="session.user?.email_verified ? 'success' : 'warning'"
                effect="plain"
              >
                {{ session.user?.email_verified ? t('settings.verified') : t('settings.unverified') }}
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
                {{ t('settings.sendVerify') }}
              </el-button>
              <el-input
                v-if="verifySent && !session.user?.email_verified"
                v-model="verifyToken"
                class="email-verify__token"
                size="small"
                :placeholder="t('settings.tokenPlaceholder')"
              >
                <template #append>
                  <el-button :loading="confirming" @click="submitVerifyToken(verifyToken)">
                    {{ t('settings.verify') }}
                  </el-button>
                </template>
              </el-input>
              <span class="node-field__help">
                {{
                  site.mailEnabled
                    ? t('settings.verifiedHint')
                    : t('settings.mailMissingHint')
                }}
              </span>
            </div>
          </el-form-item>
          <el-form-item :label="t('settings.avatar')">
            <div class="avatar-field">
              <el-avatar :size="56" :src="profile.avatar || undefined">
                {{ avatarInitial() }}
              </el-avatar>
              <el-button size="small" @click="cropperVisible = true">
                {{ t('settings.uploadAvatar') }}
              </el-button>
              <el-button
                v-if="profile.avatar"
                size="small"
                text
                @click="profile.avatar = ''"
              >
                {{ t('settings.clearAvatar') }}
              </el-button>
            </div>
            <div class="node-field__help">
              {{ t('settings.avatarHint') }}
            </div>
          </el-form-item>
          <div class="form-actions">
            <el-button type="primary" :loading="savingProfile" @click="saveProfile">
              {{ t('common.save') }}
            </el-button>
            <span class="form-actions__meta">
              {{ session.isAdmin ? t('settings.roleAdmin') : t('settings.roleUser') }} ·
              {{ t('settings.registeredAt', { date: formatTime(session.user?.created_at) }) }}
            </span>
          </div>
        </el-form>
        <HookSlot
          slot="profile"
          :context="{ user: session.user }"
          style="margin-top: 12px"
        />

        <div class="danger-zone">
          <div class="danger-zone__text">
            <strong>{{ t('settings.deleteAccount') }}</strong>
            <span class="node-field__help">
              {{
                session.isAdmin
                  ? t('settings.adminDeleteHint')
                  : t('settings.userDeleteHint')
              }}
            </span>
          </div>
          <el-button
            type="danger"
            plain
            :disabled="session.isAdmin"
            @click="openDeleteAccount"
          >
            {{ t('settings.deleteAccount') }}
          </el-button>
        </div>
      </el-card>

      <el-card v-else-if="activeSection === 'preferences'">
        <template #header>{{ t('settings.prefsHeader') }}</template>
        <el-form class="side-main__form" label-position="top">
          <el-form-item :label="t('settings.userscriptLabel')">
            <el-switch v-model="prefs.userscript_enabled" />
            <div class="node-field__help">
              {{ t('settings.userscriptHint') }}
            </div>
            <el-link
              v-if="prefs.userscript_enabled"
              type="primary"
              :href="userscriptUrl"
              target="_blank"
              rel="noopener"
              style="margin-top: 4px"
            >
              {{ t('settings.userscriptInstall') }}
            </el-link>
            <div v-if="prefs.userscript_enabled" class="node-field__help">
              {{ t('settings.userscriptSaveHint') }}
            </div>
          </el-form-item>
          <el-form-item :label="t('settings.bgPcLabel')">
            <el-input
              v-model="prefs.bg_image"
              :placeholder="t('settings.bgPcPlaceholder')"
            />
          </el-form-item>
          <el-form-item :label="t('settings.bgMobileLabel')">
            <el-input v-model="prefs.bg_image_mobile" :placeholder="t('settings.bgMobilePlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('settings.bgOpacity')">
            <el-slider v-model="opacityValue" :min="0" :max="1" :step="0.1" show-input />
            <div class="node-field__help">
              {{ t('settings.bgOpacityHint', { value: site.backgroundOpacity }) }}
              <el-link
                v-if="prefs.bg_opacity !== null"
                type="primary"
                :underline="false"
                @click="followSiteOpacity"
              >
                {{ t('settings.followSite') }}
              </el-link>
            </div>
          </el-form-item>
          <el-form-item :label="t('settings.hotlink')">
            <el-switch v-model="prefs.hotlink_enabled" />
            <div class="node-field__help">
              {{ t('settings.hotlinkHint') }}
            </div>
          </el-form-item>
          <template v-if="prefs.hotlink_enabled">
            <el-form-item :label="t('settings.allowDomains')">
              <el-input
                v-model="prefs.hotlink_allow_hosts"
                :placeholder="t('settings.allowDomainsPlaceholder')"
              />
              <div class="node-field__help">
                {{ t('settings.allowDomainsHint') }}
              </div>
            </el-form-item>
            <el-form-item :label="t('settings.allowEmptyReferer')">
              <el-switch v-model="prefs.hotlink_allow_empty" />
              <div class="node-field__help">
                {{ t('settings.allowEmptyHint') }}
              </div>
            </el-form-item>
          </template>
          <el-button type="primary" :loading="savingPrefs" @click="savePrefs">
            {{ t('common.save') }}
          </el-button>
        </el-form>
      </el-card>

      <el-card v-else-if="activeSection === 'password'">
        <template #header>
          {{ session.user?.password_set ? t('settings.passwordHeader') : t('settings.setPasswordHeader') }}
        </template>
        <p v-if="!session.user?.password_set" class="hint">
          {{ t('settings.setPasswordHint') }}
        </p>
        <el-form class="side-main__form" label-position="top">
          <!-- 统一登录建号时密码是随机值，用户不知道，所以不要求旧密码。 -->
          <el-form-item v-if="session.user?.password_set" :label="t('settings.currentPassword')">
            <el-input v-model="password.old_password" type="password" show-password />
          </el-form-item>
          <el-form-item :label="t('settings.newPassword')">
            <el-input v-model="password.new_password" type="password" show-password />
          </el-form-item>
          <el-button type="primary" :loading="changing" @click="changePassword">
            {{ session.user?.password_set ? t('settings.updatePassword') : t('settings.setPassword') }}
          </el-button>
        </el-form>
      </el-card>

      <el-card v-else-if="activeSection === 'tokens'">
        <template #header>
          <div style="display: flex; justify-content: space-between; align-items: center">
            <span>{{ t('settings.patTitle') }}</span>
            <el-button size="small" type="primary" @click="openTokenDialog">
              {{ t('settings.newToken') }}
            </el-button>
          </div>
        </template>
        <p class="hint">
          {{ t('settings.patIntro') }}
          <el-link type="primary" :href="API_DOCS_URL" target="_blank" rel="noopener noreferrer">
            {{ t('settings.apiDocs') }}
          </el-link>
        </p>
        <el-table
          v-loading="tokensLoading"
          :data="tokens"
          size="small"
          class="token-table"
        >
          <el-table-column prop="name" :label="t('common.name')" min-width="180" show-overflow-tooltip />
          <el-table-column prop="prefix" :label="t('settings.prefix')" width="92" />
          <el-table-column :label="t('settings.permission')" width="120">
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
          <el-table-column :label="t('upload.defaultAlbum')" width="112" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.album_name">{{ row.album_name }}</span>
              <el-text v-else type="info" size="small">{{ t('settings.followDefault') }}</el-text>
            </template>
          </el-table-column>
          <el-table-column :label="t('common.createdAt')" width="132">
            <template #default="{ row }">{{ formatShortTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column :label="t('settings.lastUsed')" width="132">
            <template #default="{ row }">
              {{ formatShortTime(row.last_used_at) }}
            </template>
          </el-table-column>
          <el-table-column :label="t('common.status')" width="72">
            <template #default="{ row }">
              <el-tag size="small" :type="row.revoked ? 'info' : 'success'">
                {{ row.revoked ? t('settings.statusRevoked') : t('settings.statusActive') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('common.actions')" min-width="88" align="right">
            <template #default="{ row }">
              <el-button
                link
                type="danger"
                :disabled="row.revoked"
                @click="revoke(row)"
              >
                {{ t('settings.revoke') }}
              </el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty :description="t('settings.tokensEmpty')" :image-size="60" />
          </template>
        </el-table>
      </el-card>

      <el-card v-else-if="activeSection === 'identities'">
        <template #header>{{ t('settings.identitiesHeader') }}</template>
        <p class="hint">
          {{ t('settings.oidcIntro') }}
        </p>
        <div v-for="item in identities" :key="item.name" class="identity-row">
          <div class="identity-row__main">
            <span>{{ identityTitle(item) }}</span>
            <span
              v-if="item.bound && (identityMeta(item).length || item.bound_at)"
              class="identity-meta"
            >
              <span v-for="part in identityMeta(item)" :key="part.key">{{ part.text }}</span>
              <span v-if="item.bound_at">
                {{ t('settings.boundAt', { time: formatTime(item.bound_at) }) }}
              </span>
            </span>
          </div>
          <el-tag size="small" :type="item.bound ? 'success' : 'info'">
            {{ item.bound ? t('settings.boundTag') : t('settings.unboundTag') }}
          </el-tag>
          <el-button
            v-if="item.bound"
            link
            type="danger"
            @click="unbindIdentity(item)"
          >
            {{ t('settings.unbind') }}
          </el-button>
          <el-button v-else link type="primary" @click="bindIdentity(item)">
            {{ t('settings.bind') }}
          </el-button>
        </div>
        <el-empty
          v-if="!identities.length"
          :description="t('settings.oidcDisabled')"
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

    <el-dialog v-model="deleteDialog" :title="t('settings.deleteDialogTitle')" width="420px">
      <el-alert
        type="error"
        :closable="false"
        show-icon
        :title="t('settings.deleteWarning')"
      />
      <el-form label-position="top" style="margin-top: 12px">
        <el-form-item :label="t('settings.currentPassword')">
          <el-input
            v-model="deletePassword"
            type="password"
            show-password
            :placeholder="t('settings.deletePasswordPlaceholder')"
            @keyup.enter="confirmDeleteAccount"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deleteDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="danger" :loading="deleting" @click="confirmDeleteAccount">
          {{ t('settings.deleteConfirmButton') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="tokenDialog" :title="t('settings.tokenDialogTitle')" width="440px">
      <el-form label-position="top">
        <el-form-item :label="t('settings.name')">
          <el-input v-model="tokenForm.name" maxlength="64" :placeholder="t('settings.tokenNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('upload.expire')">
          <el-select v-model="tokenForm.expires_in" style="width: 100%">
            <el-option
              v-for="option in EXPIRES"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('settings.scopes')">
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
        <el-form-item :label="t('upload.defaultAlbum')">
          <el-select
            v-model="tokenForm.album_id"
            clearable
            :placeholder="t('upload.followDefaultAlbum')"
            style="width: 100%"
          >
            <el-option
              v-for="album in tokenAlbums"
              :key="album.id"
              :label="albumName(album)"
              :value="album.id"
            />
          </el-select>
          <span class="node-field__help">
            {{ t('settings.tokenAlbumHint') }}
          </span>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="createdToken"
        type="success"
        :closable="false"
        show-icon
        :title="t('settings.tokenOnceTitle')"
      >
        <div style="display: flex; align-items: center; gap: 8px; margin-top: 8px">
          <code style="word-break: break-all">{{ createdToken }}</code>
          <el-button link type="primary" @click="copy(createdToken)">{{ t('common.copy') }}</el-button>
        </div>
      </el-alert>

      <template #footer>
        <el-button @click="tokenDialog = false">{{ t('common.close') }}</el-button>
        <el-button
          v-if="!createdToken"
          type="primary"
          :loading="tokenSaving"
          @click="createToken"
        >
          {{ t('common.create') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.identity-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.identity-row__main {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

/*: 已绑定信息：显示名 / 脱敏 subject / 绑定时间，用 · 分隔。 */
.identity-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 10px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.identity-meta > * + *::before {
  content: '·';
  margin-right: 8px;
  color: var(--el-text-color-placeholder);
}

.identity-meta code {
  font-size: 12px;
}
</style>
