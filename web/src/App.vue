<script setup>
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import en from 'element-plus/es/locale/lang/en'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import { onUnauthorized } from '@/api/client'
import { locale, t } from '@/i18n'
import AppLayout from '@/layout/AppLayout.vue'
import { useSessionStore } from '@/stores/session'
import { useSiteStore } from '@/stores/site'

const router = useRouter()
const route = useRoute()
const session = useSessionStore()
const site = useSiteStore()

//: Element Plus 自己的文案（分页、日期、空状态）跟着界面语言走。
const elementLocale = computed(() => (locale.value === 'en' ? en : zhCn))

function applyTitle() {
  const title = route.meta.title ? t(route.meta.title) : ''
  document.title = title ? `${title} · ${site.name}` : site.name
}

//: 切换语言后标题也要跟着换，不必等下一次路由跳转。
watch([locale, () => route.meta.title], applyTitle)

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
  <el-config-provider :locale="elementLocale">
    <AppLayout>
      <router-view />
    </AppLayout>
  </el-config-provider>
</template>
