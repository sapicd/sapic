<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '@/api/client'
import { t } from '@/i18n'
import { formatTime } from '@/utils/format'

const route = useRoute()

//: 后台所有页面挂在这个壳里，侧栏互相切换，避免入口分散在多处菜单里。
const items = computed(() => [
  { name: 'admin', label: t('admin.site'), icon: 'Setting' },
  { name: 'admin-hooks', label: t('admin.hooks'), icon: 'Connection' },
  { name: 'admin-backends', label: t('admin.backends'), icon: 'FolderOpened' },
  { name: 'admin-users', label: t('admin.users'), icon: 'UserFilled' },
  { name: 'admin-scheduler', label: t('admin.scheduler'), icon: 'Timer' },
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
      <div class="side-nav__title">{{ t('admin.title') }}</div>
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
          <span>{{ t('admin.version', { version: version?.current || '—' }) }}</span>
          <el-tag v-if="version?.has_update" size="small" type="danger" effect="dark">
            {{ t('admin.updatable') }}
          </el-tag>
        </button>
      </div>
    </aside>

    <section class="side-main">
      <router-view />
    </section>

    <el-dialog v-model="versionDialog" :title="t('admin.versionInfo')" width="440px">
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item :label="t('admin.current')">
          {{ version?.current ? `v${version.current}` : '—' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('admin.latest')">
          {{ version?.latest ? `v${version.latest}` : '—' }}
          <el-tag
            v-if="version?.has_update"
            size="small"
            type="danger"
            effect="plain"
            style="margin-left: 8px"
          >
            {{ t('admin.updatable') }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('admin.releasedAt')">
          {{ version?.released_at ? formatTime(version.released_at) : '—' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('admin.checkedAt')">
          {{ version?.checked_at ? formatTime(version.checked_at) : t('admin.notChecked') }}
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
        :title="t('admin.updateCheckDisabled')"
      />
      <p v-if="version?.has_update" class="hint">
        {{ t('admin.updateHint') }}
      </p>

      <template #footer>
        <div class="version-footer">
          <el-link
            v-if="version?.url"
            type="primary"
            :underline="false"
            :href="version.url"
            target="_blank"
            rel="noopener"
          >
            {{ t('admin.releasePage') }}
          </el-link>
          <span v-else />

          <div class="version-footer__actions">
            <el-button :loading="versionLoading" @click="loadVersion(true)">
              {{ t('admin.recheck') }}
            </el-button>
            <el-button type="primary" @click="versionDialog = false">
              {{ t('common.close') }}
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/*: 发布页链接靠左、按钮靠右，避免三个控件挤在右下角。 */
.version-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.version-footer__actions {
  display: flex;
  align-items: center;
}

/*: 两个按钮之间只保留 Element 自带的间距，不叠加外层 gap。 */
.version-footer__actions :deep(.el-button + .el-button) {
  margin-left: 12px;
}
</style>
