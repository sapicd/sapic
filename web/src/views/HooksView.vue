<script setup>
import { computed, onMounted, ref } from 'vue'

import { api, errorMessage } from '@/api/client'
import HookConfigForm from '@/components/hook/HookConfigForm.vue'

const CATALOGS = {
  upload: '存储',
  processor: '处理',
  auth: '鉴权',
  mail: '邮件',
}

const tab = ref('hooks')
const manifests = ref([])
const configs = ref([])
const loading = ref(false)
const reloading = ref(false)
const saving = ref('')
const pinging = ref('')
const toggling = ref('')
const removing = ref('')

const importDialog = ref(false)
const importModule = ref('')
const importing = ref(false)

const enabledCount = computed(
  () => manifests.value.filter((item) => item.enabled).length,
)

async function loadHooks() {
  loading.value = true
  try {
    const data = await api.get('/hooks')
    manifests.value = data?.items || []
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载钩子清单失败'))
  } finally {
    loading.value = false
  }
}

async function loadConfigs() {
  try {
    const data = await api.get('/hooks/config')
    configs.value = data?.items || []
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载钩子配置失败'))
  }
}

async function refresh() {
  await loadHooks()
  await loadConfigs()
}

async function reloadHooks() {
  reloading.value = true
  try {
    await api.post('/hooks/reload')
    await refresh()
    ElMessage.success('钩子管理器已重载')
  } catch (error) {
    ElMessage.error(errorMessage(error, '重载失败'))
  } finally {
    reloading.value = false
  }
}

function openImport() {
  importModule.value = ''
  importDialog.value = true
}

async function importHook() {
  const module = importModule.value.trim()
  if (!module) {
    ElMessage.warning('请输入模块名')
    return
  }
  importing.value = true
  try {
    await api.post('/hooks/import', { json: { module } })
    importDialog.value = false
    await refresh()
    ElMessage.success('钩子已导入')
  } catch (error) {
    ElMessage.error(errorMessage(error, '导入失败'))
  } finally {
    importing.value = false
  }
}

async function removeHook(row) {
  try {
    await ElMessageBox.confirm(
      `确定移除钩子「${row.name}」吗？已安装的 Python 包不会被卸载。`,
      '移除钩子',
      { type: 'warning' },
    )
  } catch (error) {
    return
  }
  removing.value = row.name
  try {
    await api.del(`/hooks/import/${row.name}`)
    await refresh()
    ElMessage.success('已移除')
  } catch (error) {
    ElMessage.error(errorMessage(error, '移除失败'))
  } finally {
    removing.value = ''
  }
}

async function toggleHook(row, enabled) {
  toggling.value = row.name
  try {
    const data = await api.patch(`/hooks/${row.name}`, { json: { enabled } })
    row.enabled = data?.enabled ?? enabled
    const config = configs.value.find((item) => item.name === row.name)
    if (config) config.enabled = row.enabled
    ElMessage.success(row.enabled ? '已启用' : '已禁用')
  } catch (error) {
    ElMessage.error(errorMessage(error, '操作失败'))
  } finally {
    toggling.value = ''
  }
}

async function saveConfig(item, values) {
  saving.value = item.name
  try {
    const data = await api.put(`/hooks/config/${item.name}`, { json: values })
    item.values = data?.values || values
    ElMessage.success('配置已保存')
  } catch (error) {
    ElMessage.error(errorMessage(error, '保存失败'))
  } finally {
    saving.value = ''
  }
}

async function pingHook(item, values) {
  pinging.value = item.name
  try {
    const data = await api.post(`/hooks/${item.name}/actions/ping`, {
      json: { values },
    })
    if (data?.code === 0) {
      ElMessage.success(data?.toast?.text || '检测通过')
    } else {
      ElMessage.error(data?.message || '检测未通过')
    }
  } catch (error) {
    ElMessage.error(errorMessage(error, '检测失败'))
  } finally {
    pinging.value = ''
  }
}

onMounted(refresh)
</script>

<template>
  <div v-loading="loading" class="page">
    <div class="page__header">
      <h2 class="page__title">钩子管理</h2>
      <el-button @click="refresh">刷新</el-button>
    </div>

    <el-card>
      <el-tabs v-model="tab">
        <el-tab-pane label="钩子扩展" name="hooks">
          <div class="toolbar hook-toolbar">
            <el-button type="primary" :loading="reloading" @click="reloadHooks">
              重载钩子管理器
            </el-button>
            <el-button @click="openImport">导入钩子</el-button>
            <span class="toolbar__meta">
              共 {{ manifests.length }} 个钩子，已启用 {{ enabledCount }} 个（禁用后其插槽与动作立即失效）
            </span>
          </div>

          <el-empty v-if="!manifests.length" description="没有可用钩子" :image-size="60" />
          <el-table v-else :data="manifests" row-key="name" style="width: 100%">
            <el-table-column label="名称" min-width="150">
              <template #default="{ row }">
                <span :title="row.title">{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="version" label="版本" width="90" />
            <el-table-column prop="author" label="作者" width="130" show-overflow-tooltip />
            <el-table-column
              prop="description"
              label="描述"
              min-width="200"
              show-overflow-tooltip
            />
            <el-table-column label="类型" width="90">
              <template #default="{ row }">
                {{ CATALOGS[row.catalog] || row.catalog || '其他' }}
              </template>
            </el-table-column>
            <el-table-column label="来源" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="row.family === 'third' ? 'warning' : 'info'" effect="plain">
                  {{ row.family === 'third' ? '第三方' : '本地' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-switch
                  :model-value="row.enabled"
                  :loading="toggling === row.name"
                  active-text="启用"
                  inactive-text="禁用"
                  inline-prompt
                  @change="(value) => toggleHook(row, value)"
                />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="90" align="right">
              <template #default="{ row }">
                <el-button
                  v-if="row.family === 'third'"
                  link
                  type="danger"
                  :loading="removing === row.name"
                  @click="removeHook(row)"
                >
                  移除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="钩子配置" name="config">
          <p class="hint">
            这里保存各钩子的默认配置；具体存储后端中已填写的同名字段会覆盖此处的值。
          </p>

          <el-empty
            v-if="!configs.length"
            description="没有需要配置的钩子"
            :image-size="60"
          />
          <HookConfigForm
            v-for="item in configs"
            :key="item.name"
            :config="item"
            :saving="saving === item.name"
            :pinging="pinging === item.name"
            @save="(values) => saveConfig(item, values)"
            @ping="(values) => pingHook(item, values)"
          />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="importDialog" title="导入钩子" width="480px">
      <el-form label-position="top">
        <el-form-item label="模块名">
          <el-input
            v-model="importModule"
            placeholder="如 sapic_hook_cos（需已安装到运行 sapic 的 Python 环境）"
            @keyup.enter="importHook"
          />
        </el-form-item>
      </el-form>
      <p class="hint">
        钩子是被声明式加载的 Python 模块，要求提供
        <code>__version__</code> 与 <code>__author__</code>，并实现
        <code>hook_manifest()</code> 或 <code>upimg_save</code> /
        <code>upimg_delete</code> 等约定函数。导入只是把模块加入加载列表，请先
        <code>pip install</code> 对应包。
      </p>
      <template #footer>
        <el-button @click="importDialog = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="importHook">
          导入
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
