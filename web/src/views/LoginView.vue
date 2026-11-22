<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { errorMessage } from '@/api/client'
import HookSlot from '@/components/hook/HookSlot.vue'
import { t } from '@/i18n'
import { useSessionStore } from '@/stores/session'
import { useSiteStore } from '@/stores/site'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const site = useSiteStore()

const form = reactive({ username: '', password: '' })
const loading = ref(false)

//: OIDC 回调失败时会带 ?oidc=<flag> 回到登录页，这里给出可读的说明。
//: 文案在词表的 ``auth.oidc.<flag>`` 下，flag 只做白名单校验。
const OIDC_ERRORS = ['denied', 'unlinked', 'inactive', 'invalid', 'provider', 'error']

const oidcStatus = ref('')

const oidcError = computed(() =>
  oidcStatus.value
    ? {
        title: t(`auth.oidc.${oidcStatus.value}.title`),
        description: t(`auth.oidc.${oidcStatus.value}.description`),
      }
    : null,
)

onMounted(() => {
  const status = typeof route.query.oidc === 'string' ? route.query.oidc : ''
  oidcStatus.value = OIDC_ERRORS.includes(status) ? status : ''
})

async function submit() {
  if (!form.username || !form.password) {
    ElMessage.warning(t('auth.credentialsRequired'))
    return
  }
  loading.value = true
  try {
    await session.login({ ...form })
    ElMessage.success(t('auth.loginSuccess'))
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : null
    router.push(redirect || { name: 'upload' })
  } catch (error) {
    ElMessage.error(errorMessage(error, t('auth.loginFailed')))
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
      <p v-if="site.loginNotice" class="auth__subtitle">{{ site.loginNotice }}</p>
      <el-alert
        v-if="oidcError"
        class="auth__alert"
        type="error"
        show-icon
        :title="oidcError.title"
        :description="oidcError.description"
        @close="oidcStatus = ''"
      />
      <el-alert
        v-if="!site.passwordLogin"
        type="info"
        :closable="false"
        show-icon
        :title="t('auth.passwordDisabledTitle')"
        :description="t('auth.passwordDisabledDesc')"
      />
      <el-form v-else label-position="top" @submit.prevent="submit">
        <el-form-item :label="t('auth.username')">
          <el-input
            v-model="form.username"
            autocomplete="username"
            :placeholder="t('auth.usernamePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('auth.password')">
          <el-input
            v-model="form.password"
            type="password"
            :placeholder="t('auth.passwordPlaceholder')"
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
          {{ t('auth.signIn') }}
        </el-button>
      </el-form>

      <HookSlot slot="login.after_form" />

      <div v-if="site.passwordLogin && site.allowRegister" class="auth__footer">
        {{ t('auth.noAccount') }}
        <router-link :to="{ name: 'register' }"> {{ t('auth.signUp') }} </router-link>
      </div>
    </el-card>
  </div>
</template>
