<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

//: 后台所有页面挂在这个壳里，侧栏互相切换，避免入口分散在多处菜单里。
const items = [
  { name: 'admin', label: '站点设置', icon: 'Setting' },
  { name: 'admin-hooks', label: '钩子管理', icon: 'Connection' },
  { name: 'admin-backends', label: '存储后端', icon: 'FolderOpened' },
  { name: 'admin-users', label: '用户管理', icon: 'UserFilled' },
]

const activeName = computed(() => String(route.name || ''))
</script>

<template>
  <div class="page side-shell">
    <aside class="side-nav">
      <div class="side-nav__title">后台管理</div>
      <nav class="side-nav__menu">
        <router-link
          v-for="item in items"
          :key="item.name"
          :to="{ name: item.name }"
          class="side-nav__link"
          :class="{ 'is-active': activeName === item.name }"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </router-link>
      </nav>
    </aside>
    <section class="side-main">
      <router-view />
    </section>
  </div>
</template>
