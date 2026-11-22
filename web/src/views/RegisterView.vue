<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { errorMessage } from '@/api/client'
import { t } from '@/i18n'
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
    ElMessage.success(t('auth.registerSuccess'))
    router.push({ name: 'login' })
  } catch (error) {
    ElMessage.error(errorMessage(error, t('auth.registerFailed')))
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
      <p class="auth__subtitle">{{ t('auth.registerHint') }}</p>
      <el-alert
        v-if="!site.passwordLogin"
        type="warning"
        :closable="false"
        show-icon
        :title="t('auth.registerDisabledTitle')"
        :description="t('auth.registerDisabledDesc')"
      />
      <el-form v-else label-position="top" @submit.prevent="submit">
        <el-form-item :label="t('auth.username')">
          <el-input
            v-model="form.username"
            :placeholder="t('auth.usernamePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('auth.email')">
          <el-input v-model="form.email" :placeholder="t('auth.emailPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('auth.password')">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="t('auth.passwordHint')"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button
          type="primary"
          style="width: 100%"
          :loading="loading"
          @click="submit"
        >
          {{ t('auth.signUp') }}
        </el-button>
      </el-form>
      <div v-if="site.passwordLogin" class="auth__footer">
        {{ t('auth.haveAccount') }}
        <router-link :to="{ name: 'login' }"> {{ t('auth.signIn') }} </router-link>
      </div>
    </el-card>
  </div>
</template>
