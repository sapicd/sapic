<script setup>
import { computed, onMounted, ref } from 'vue'

import { api, errorMessage } from '@/api/client'
import HookBlock from '@/components/hook/HookBlock.vue'
import HookSlot from '@/components/hook/HookSlot.vue'
import { manifestNodes } from '@/components/hook/manifest'

const manifests = ref([])
const loading = ref(false)

const installed = computed(() => manifests.value.length)

async function loadHooks() {
  loading.value = true
  try {
    const data = await api.get('/hooks/manifests')
    manifests.value = data?.items || []
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载钩子清单失败'))
  } finally {
    loading.value = false
  }
}

onMounted(loadHooks)
</script>

<template>
  <div v-loading="loading" class="page">
    <div class="page__header">
      <h2 class="page__title">钩子管理</h2>
      <el-button @click="loadHooks">刷新</el-button>
    </div>

    <el-card>
      <template #header>已安装钩子（{{ installed }}）</template>
      <el-empty v-if="!installed" description="没有可用钩子" :image-size="60" />
      <div v-else class="hook-slot">
        <HookBlock
          v-for="manifest in manifests"
          :key="manifest.name"
          :hook="manifest.name"
          :title="manifest.title"
          :nodes="manifestNodes(manifest)"
          :context="{ manifest }"
          show-title
          :refresh="loadHooks"
        />
      </div>
    </el-card>

    <HookSlot
      slot="admin.hook_setting"
      :context="{ manifest: null }"
      show-title
      style="margin-top: 16px"
    />
  </div>
</template>
