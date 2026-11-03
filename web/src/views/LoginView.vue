<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { errorMessage } from '@/api/client'
import HookSlot from '@/components/hook/HookSlot.vue'
import { useSessionStore } from '@/stores/session'
import { useSiteStore } from '@/stores/site'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const site = useSiteStore()

const form = reactive({ username: '', password: '' })
const loading = ref(false)

//: OIDC 回调失败时会带 ?oidc=<flag> 回到登录页，这里给出可读的说明。
const OIDC_ERRORS = {
  denied: {
    title: '已取消 Passport 授权',
    description: '如需登录，请重新点击「通过 Passport 登录」。',
  },
  unlinked: {
    title: 'Passport 账号无法登录',
    description:
      '该 Passport 账号暂时无法关联本地用户，请联系管理员检查统一登录配置或账号状态。',
  },
  inactive: {
    title: '账号状态受限',
    description: '该账号待审核或已被禁用，请联系管理员处理。',
  },
  invalid: {
    title: 'Passport 身份信息无效',
    description: 'Provider 未返回必要的 subject，请联系管理员检查 OIDC 配置。',
  },
  error: {
    title: 'Passport 登录失败',
    description: '请重试；若持续失败，请联系管理员查看后端日志。',
  },
}

const oidcError = ref(null)

onMounted(() => {
  const status = typeof route.query.oidc === 'string' ? route.query.oidc : ''
  oidcError.value = OIDC_ERRORS[status] || null
})

async function submit() {
  if (!form.username || !form.password) {
    ElMessage.warning('请填写用户名和密码')
    return
  }
  loading.value = true
  try {
    await session.login({ ...form })
    ElMessage.success('登录成功')
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : null
    router.push(redirect || { name: 'upload' })
  } catch (error) {
    ElMessage.error(errorMessage(error, '登录失败'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth">
    <el-card class="auth__card">
      <div class="auth__brand">
        <img :src="site.logoUrl" :alt="site.name" />
      </div>
      <p class="auth__subtitle">登录后可上传与管理图片</p>
      <el-alert
        v-if="oidcError"
        class="auth__alert"
        type="error"
        show-icon
        :title="oidcError.title"
        :description="oidcError.description"
        @close="oidcError = null"
      />
      <el-alert
        v-if="!site.passwordLogin"
        type="info"
        :closable="false"
        show-icon
        title="本站已关闭密码登录"
        description="请使用下方统一登录方式进入，如有问题请联系管理员"
      />
      <el-form v-else label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名">
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            autocomplete="current-password"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button
          type="primary"
          style="width: 100%"
          :loading="loading"
          @click="submit"
        >
          登录
        </el-button>
      </el-form>

      <HookSlot slot="login.after_form" />

      <div v-if="site.passwordLogin && site.allowRegister" class="auth__footer">
        还没有账号？<router-link :to="{ name: 'register' }">注册</router-link>
      </div>
    </el-card>
  </div>
</template>
