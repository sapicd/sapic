<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import HookSlot from '@/components/hook/HookSlot.vue'
import { useSessionStore } from '@/stores/session'
import { useSiteStore } from '@/stores/site'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const site = useSiteStore()

const year = new Date().getFullYear()
const stuck = ref(false)
const mobile = ref(false)
const announcementVisible = ref(true)
const aboutVisible = ref(false)

let viewport = null

const backgroundStyle = computed(() => {
  //: 个人背景优先于站点背景；透明度用 ?? 而非 ||，0 是合法的「完全透明」。
  const personal = mobile.value
    ? session.settings.bg_image_mobile || session.settings.bg_image
    : session.settings.bg_image
  const url = personal || (mobile.value && site.backgroundMobile) || site.background
  const opacity = session.settings.bg_opacity ?? site.backgroundOpacity
  return {
    backgroundImage: `url("${url || '/background.jpg'}")`,
    '--app-overlay': String(opacity),
  }
})

const menus = computed(() => {
  const items = [{ name: 'upload', label: '首页', icon: 'HomeFilled' }]
  if (site.plazaEnabled) {
    items.push({ name: 'plaza', label: '广场', icon: 'Grid' })
  }
  if (session.authenticated) {
    items.push({ name: 'images', label: '图片', icon: 'Picture' })
    items.push({ name: 'albums', label: '相册', icon: 'FolderOpened' })
    items.push({ name: 'settings', label: '设置', icon: 'Setting' })
  }
  return items
})

const activeName = computed(() => {
  if (route.name === 'image-detail') return 'images'
  return String(route.name || '')
})

//: 后台统一从这一个入口进，具体页面由 AdminLayout 的侧栏切换。
const adminActive = computed(() => route.path.startsWith('/admin'))

const initial = computed(() => (session.displayName || '?').slice(0, 1).toUpperCase())

function onScroll() {
  stuck.value = window.scrollY > 8
}

function onViewportChange(event) {
  mobile.value = event.matches
}

onMounted(() => {
  onScroll()
  window.addEventListener('scroll', onScroll, { passive: true })
  viewport = window.matchMedia('(max-width: 768px)')
  mobile.value = viewport.matches
  viewport.addEventListener('change', onViewportChange)
})

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
  viewport?.removeEventListener('change', onViewportChange)
})

async function onCommand(command) {
  if (command === 'logout') {
    await session.logout()
    ElMessage.success('已退出登录')
    router.push({ name: 'login' })
    return
  }
  router.push({ name: command })
}
</script>

<template>
  <div class="app">
    <div class="app-bg" :style="backgroundStyle"></div>

    <header class="app-header" :class="{ 'is-stuck': stuck }">
      <div class="app-header__inner">
        <router-link :to="{ name: 'upload' }" class="app-brand">
          <img class="app-brand__logo" :src="site.logoUrl" :alt="site.name" />
        </router-link>

        <div class="app-header__right">
          <nav class="app-nav">
            <router-link
              v-for="item in menus"
              :key="item.name"
              :to="{ name: item.name }"
              class="app-nav__item"
              :class="{ 'is-active': activeName === item.name }"
            >
              <el-icon><component :is="item.icon" /></el-icon>
              <span>{{ item.label }}</span>
            </router-link>

            <router-link
              v-if="session.isAdmin"
              :to="{ name: 'admin' }"
              class="app-nav__item"
              :class="{ 'is-active': adminActive }"
            >
              <el-icon><Tools /></el-icon>
              <span>后台管理</span>
            </router-link>
          </nav>

          <div class="app-user">
            <el-dropdown v-if="session.authenticated" trigger="click" @command="onCommand">
              <span class="app-user__name">
                <el-avatar
                  class="app-user__avatar"
                  :size="26"
                  :src="session.user?.avatar || undefined"
                >
                  {{ initial }}
                </el-avatar>
                {{ session.displayName }}
                <el-icon><ArrowDown /></el-icon>
              </span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="logout">退出登录</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <template v-else>
              <router-link class="app-nav__item" :to="{ name: 'login' }">
                <el-icon><Key /></el-icon>
                <span>登录</span>
              </router-link>
              <router-link
                v-if="site.allowRegister"
                class="app-nav__item"
                :to="{ name: 'register' }"
              >
                <el-icon><User /></el-icon>
                <span>注册</span>
              </router-link>
            </template>
          </div>
        </div>
      </div>
    </header>

    <div v-if="site.announcement && announcementVisible" class="app-announcement">
      <el-alert
        type="info"
        show-icon
        :closable="true"
        :title="site.announcement"
        @close="announcementVisible = false"
      />
    </div>

    <main class="app-main">
      <slot />
    </main>

    <footer class="app-footer">
      <HookSlot slot="nav" />
      <p class="app-footer__copy">
        <a v-if="site.icp" href="https://beian.miit.gov.cn/" target="_blank" rel="noopener">
          {{ site.icp }}
        </a>
        <a v-if="site.about" class="app-footer__about" @click="aboutVisible = true">About</a>
        Copyright &copy; {{ year }} {{ site.footer }} Powered by
        <a
          href="https://github.com/sapicd/sapic"
          target="_blank"
          rel="noopener"
          :title="site.version ? `Version ${site.version}` : undefined"
          >sapic</a
        >
      </p>
    </footer>

    <el-dialog v-model="aboutVisible" title="关于本站" width="420px">
      <p class="app-about">{{ site.about }}</p>
    </el-dialog>
  </div>
</template>
