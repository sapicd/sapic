<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '@/api/client'
import { formatTime } from '@/utils/format'

const route = useRoute()

//: 后台所有页面挂在这个壳里，侧栏互相切换，避免入口分散在多处菜单里。
const items = computed(() => [
  { name: 'admin', label: '站点设置', icon: 'Setting' },
  { name: 'admin-hooks', label: '钩子管理', icon: 'Connection' },
  { name: 'admin-backends', label: '存储后端', icon: 'FolderOpened' },
  { name: 'admin-users', label: '用户管理', icon: 'UserFilled' },
])

//: ``/admin`` 上的默认子路由没有命名，按「站点设置」高亮。
const activeName = computed(() => String(route.name || 'admin'))

//: 版本检测只服务后台：进后台拉一次，未启用或网络失败都静默，不打扰管理员。
const version = ref(null)
const versionLoading = ref(false)
const versionDialog = ref(false)

async function loadVersion(refreshNow = false) {
  versionLoading.value = true
  try {
    version.value = await api.get('/settings/version', {
      query: refreshNow ? { refresh: 1 } : {},
    })
  } catch (error) {
    version.value = null
  } finally {
    versionLoading.value = false
  }
}

onMounted(() => loadVersion())
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

      <div class="side-nav__foot">
        <button type="button" class="side-nav__version" @click="versionDialog = true">
          <span>版本 v{{ version?.current || '—' }}</span>
          <el-tag v-if="version?.has_update" size="small" type="danger" effect="dark">
            可更新
          </el-tag>
        </button>
      </div>
    </aside>

    <section class="side-main">
      <router-view />
    </section>

    <el-dialog v-model="versionDialog" title="版本信息" width="440px">
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="当前版本">
          v{{ version?.current || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="最新版本">
          {{ version?.latest || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="发布时间">
          {{ version?.released_at ? formatTime(version.released_at) : '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="检查时间">
          {{ version?.checked_at ? formatTime(version.checked_at) : '未检查' }}
        </el-descriptions-item>
      </el-descriptions>

      <el-alert
        v-if="version?.error"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top: 12px"
        :title="version.error"
      />
      <el-alert
        v-else-if="version && !version.enabled"
        type="info"
        :closable="false"
        show-icon
        style="margin-top: 12px"
        title="未启用更新检测（sapic_updatecheckurl 为空）"
      />
      <p v-if="version?.has_update" class="hint">
        有新版本可用，升级前请先备份数据库与上传目录。
      </p>

      <template #footer>
        <el-link
          v-if="version?.url"
          type="primary"
          :underline="false"
          :href="version.url"
          target="_blank"
          rel="noopener"
        >
          打开发布页
        </el-link>
        <el-button :loading="versionLoading" @click="loadVersion(true)">
          重新检查
        </el-button>
        <el-button type="primary" @click="versionDialog = false">
          关闭
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
