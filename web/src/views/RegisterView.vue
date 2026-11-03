<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { errorMessage } from '@/api/client'
import { useSessionStore } from '@/stores/session'
import { useSiteStore } from '@/stores/site'

const router = useRouter()
const session = useSessionStore()
const site = useSiteStore()

const form = reactive({ username: '', email: '', password: '' })
const loading = ref(false)

async function submit() {
  loading.value = true
  try {
    await session.register({ ...form })
    ElMessage.success('注册成功，请登录')
    router.push({ name: 'login' })
  } catch (error) {
    ElMessage.error(errorMessage(error, '注册失败'))
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
      <p class="auth__subtitle">创建一个账号，开始使用</p>
      <el-alert
        v-if="!site.passwordLogin"
        type="warning"
        :closable="false"
        show-icon
        title="本站已关闭账号注册"
        description="请通过统一登录进入；还没有账号请联系管理员"
      />
      <el-form v-else label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="4-32 位，字母开头" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="可选，用于找回密码" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button
          type="primary"
          style="width: 100%"
          :loading="loading"
          @click="submit"
        >
          注册
        </el-button>
      </el-form>
      <div v-if="site.passwordLogin" class="auth__footer">
        已有账号？<router-link :to="{ name: 'login' }">登录</router-link>
      </div>
    </el-card>
  </div>
</template>
