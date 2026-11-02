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

//: OIDC 回调出错时会带 ?oidc=error|denied 回到登录页。
const OIDC_ERRORS = {
  error: 'Passport 登录失败，请重试或联系管理员',
  denied: '已取消 Passport 授权',
}

onMounted(() => {
  const status = typeof route.query.oidc === 'string' ? route.query.oidc : ''
  if (status && OIDC_ERRORS[status]) ElMessage.warning(OIDC_ERRORS[status])
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
      <el-form label-position="top" @submit.prevent="submit">
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

      <div class="auth__footer">
        还没有账号？<router-link :to="{ name: 'register' }">注册</router-link>
      </div>
    </el-card>
  </div>
</template>
