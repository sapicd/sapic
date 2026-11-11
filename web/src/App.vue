<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import zhCn from 'element-plus/es/locale/lang/zh-cn'

import { onUnauthorized } from '@/api/client'
import AppLayout from '@/layout/AppLayout.vue'
import { useSessionStore } from '@/stores/session'

const router = useRouter()
const session = useSessionStore()

onMounted(() => {
  onUnauthorized(() => {
    session.reset()
    const current = router.currentRoute.value
    if (current.name !== 'login') {
      router.push({ name: 'login', query: { redirect: current.fullPath } })
    }
  })
})
</script>

<template>
  <el-config-provider :locale="zhCn">
    <AppLayout>
      <router-view />
    </AppLayout>
  </el-config-provider>
</template>
