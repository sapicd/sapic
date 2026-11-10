<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { api, errorMessage } from '@/api/client'
import HookConfigForm from '@/components/hook/HookConfigForm.vue'
import { formatTime } from '@/utils/format'

const router = useRouter()

const CATALOGS = {
  upload: '存储',
  processor: '处理',
  auth: '鉴权',
  mail: '邮件',
}

//: 市场列表的 status 由第三方数据给出，只做展示映射，不认识的值原样显示。
const MARKET_STATUS = {
  stable: '正式版',
  production: '正式版',
  ga: '正式版',
  beta: '公测版',
  rc: '预发布',
  archive: '已封存',
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

//: 钩子市场：远端列表 + 本地安装状态（后端合并好的 installed/loaded）。
//: 列表由后端分页，这里只保存当前页与总数。
const marketItems = ref([])
const marketMeta = ref({ configured: true, storage_dir: '', updated_at: 0 })
const marketError = ref('')
const marketLoading = ref(false)
const marketLoaded = ref(false)
const marketTotal = ref(0)
const marketPage = ref(1)
const marketPageSize = ref(10)
const busyItem = ref('')

const installForm = ref({ package: '', module: '', index_url: '', upgrade: false })
const installDialog = ref(false)
const installing = ref(false)
const installLog = ref('')
const installResult = ref(true)

const enabledCount = computed(
  () => manifests.value.filter((item) => item.enabled).length,
)

//: 禁用的钩子不可用，配置项也就没有必要暴露出来。
const enabledConfigs = computed(() =>
  configs.value.filter((item) => item.enabled),
)

//: 存储驱动（catalog=upload）的凭据只在「存储后端」配置，这里不再重复一份表单。
const uploadConfigs = computed(() =>
  enabledConfigs.value.filter((item) => item.catalog === 'upload'),
)

const otherConfigs = computed(() =>
  enabledConfigs.value.filter((item) => item.catalog !== 'upload'),
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

//: 市场列表走 GitHub 接口，切到该页签再拉，避免每次进后台都请求外网。
watch(tab, (value) => {
  if (value === 'market' && !marketLoaded.value) loadMarket()
})

async function loadMarket(refreshNow = false) {
  marketLoading.value = true
  marketError.value = ''
  try {
    const data = await api.get('/hooks/market', {
      query: {
        page: marketPage.value,
        page_size: marketPageSize.value,
        ...(refreshNow ? { refresh: 1 } : {}),
      },
    })
    marketItems.value = data?.items || []
    marketTotal.value = data?.total || 0
    //: 列表变短时后端把页码收敛到最后一页，前端跟着同步。
    if (data?.page) marketPage.value = data.page
    marketMeta.value = {
      configured: data?.configured !== false,
      storage_dir: data?.storage_dir || '',
      market_url: data?.market_url || '',
      updated_at: data?.updated_at || 0,
    }
    marketLoaded.value = true
  } catch (error) {
    marketError.value = errorMessage(error, '加载钩子市场失败')
  } finally {
    marketLoading.value = false
  }
}

//: 刷新远端缓存时回到第一页，否则停留在原来的页码容易看到空表。
function refreshMarket() {
  marketPage.value = 1
  return loadMarket(true)
}

function changeMarketPage(page) {
  marketPage.value = page
  loadMarket()
}

function changeMarketPageSize(size) {
  marketPageSize.value = size
  marketPage.value = 1
  loadMarket()
}

function openInstall(item) {
  installForm.value = {
    package: item?.package || '',
    module: item?.module || '',
    index_url: '',
    upgrade: Boolean(item?.installed),
  }
  installLog.value = ''
  installResult.value = true
  installDialog.value = true
}

function openCustomInstall() {
  installForm.value = { package: '', module: '', index_url: '', upgrade: false }
  installLog.value = ''
  installResult.value = true
  installDialog.value = true
}

async function submitInstall() {
  const packageName = installForm.value.package.trim()
  if (!packageName) {
    ElMessage.warning('请输入包名')
    return
  }
  installing.value = true
  installLog.value = ''
  try {
    const data = await api.post('/hooks/install', {
      json: { ...installForm.value, package: packageName },
    })
    const result = data?.install || {}
    installResult.value = Boolean(result.ok)
    installLog.value = result.output || ''
    if (result.ok) {
      ElMessage.success('安装成功')
      installDialog.value = false
      await Promise.all([refresh(), loadMarket()])
    }
  } catch (error) {
    installResult.value = false
    installLog.value = errorMessage(error, '安装失败')
  } finally {
    installing.value = false
  }
}

async function importMarketItem(item) {
  busyItem.value = item.module
  try {
    await api.post('/hooks/import', { json: { module: item.module } })
    ElMessage.success('钩子已引入')
    await Promise.all([refresh(), loadMarket()])
  } catch (error) {
    ElMessage.error(errorMessage(error, '引入失败'))
  } finally {
    busyItem.value = ''
  }
}

async function purgePackage(item) {
  try {
    await ElMessageBox.confirm(
      `确定卸载「${item.name}」吗？会删除 ${marketMeta.value.storage_dir || '包目录'} 下的包文件，且不可恢复。`,
      '卸载第三方包',
      { type: 'warning' },
    )
  } catch (error) {
    return
  }
  busyItem.value = item.module
  try {
    await api.del(`/hooks/import/${item.module}`, { query: { purge: 1 } })
    ElMessage.success('已卸载')
    await Promise.all([refresh(), loadMarket()])
  } catch (error) {
    ElMessage.error(errorMessage(error, '卸载失败'))
  } finally {
    busyItem.value = ''
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
            这里配置鉴权、处理、邮件类钩子的参数；存储驱动的凭据统一在「存储后端」里填写。
          </p>

          <el-alert
            v-if="uploadConfigs.length"
            type="info"
            :closable="false"
            show-icon
            style="margin-bottom: 16px"
          >
            <template #title>
              存储驱动（{{ uploadConfigs.map((item) => item.title).join('、') }}）的凭据在「存储后端」配置
            </template>
            <el-button link type="primary" @click="router.push({ name: 'admin-backends' })">
              去存储后端
            </el-button>
          </el-alert>

          <el-empty
            v-if="!otherConfigs.length"
            description="没有需要配置的钩子（禁用的钩子不显示配置项）"
            :image-size="60"
          />
          <HookConfigForm
            v-for="item in otherConfigs"
            :key="item.name"
            :config="item"
            :saving="saving === item.name"
            :pinging="pinging === item.name"
            @save="(values) => saveConfig(item, values)"
            @ping="(values) => pingHook(item, values)"
          />
        </el-tab-pane>

        <el-tab-pane label="钩子市场" name="market">
          <el-alert
            v-if="!marketMeta.configured"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 12px"
            title="未配置第三方包目录，暂时不能在后台安装扩展"
            description="设置 sapic_hookpkgstoragedir（如 data/hooks）后重启服务；该目录会被加入 sys.path 并作为钩子扫描路径。"
          />

          <div class="toolbar hook-toolbar">
            <el-button :loading="marketLoading" @click="refreshMarket">
              刷新列表
            </el-button>
            <el-button @click="openCustomInstall">手动安装</el-button>
            <span class="toolbar__meta">
              共 {{ marketTotal }} 个扩展<template v-if="marketMeta.updated_at">
                · 列表缓存于 {{ formatTime(marketMeta.updated_at) }}</template
              >
            </span>
          </div>

          <el-alert
            v-if="marketError"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 12px"
            :title="marketError"
          />
          <p class="hint">
            列表取自官方仓库的 list.json（可用 sapic_hookmarketurl 指向镜像），只显示声明
            <code>appversion: "2.x"</code> 的扩展——V1 钩子与本版本的契约不兼容；本地已加载的除外。
            安装会把包 pip 到 <code>{{ marketMeta.storage_dir || '包目录' }}</code
            >，再「引入」后即出现在「钩子扩展」里。
          </p>

          <el-empty
            v-if="!marketLoading && !marketItems.length"
            description="没有可用的市场数据"
            :image-size="60"
          />
          <el-table
            v-else
            v-loading="marketLoading"
            :data="marketItems"
            row-key="module"
            style="width: 100%"
          >
            <el-table-column label="名称" min-width="150">
              <template #default="{ row }">
                <div class="market-name">
                  <span>{{ row.name }}</span>
                  <el-tag v-if="row.loaded" size="small" type="success" effect="plain">
                    已加载
                  </el-tag>
                </div>
                <span class="market-module">{{ row.module }}</span>
              </template>
            </el-table-column>
            <el-table-column
              prop="description"
              label="描述"
              min-width="200"
              show-overflow-tooltip
            />
            <el-table-column label="作者" width="120" show-overflow-tooltip>
              <template #default="{ row }">
                <el-link
                  v-if="row.home"
                  type="primary"
                  :underline="false"
                  :href="row.home"
                  target="_blank"
                  rel="noopener"
                >
                  {{ row.author || row.name }}
                </el-link>
                <span v-else>{{ row.author || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">
                  {{ MARKET_STATUS[row.status] || row.status || '未知' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="已装版本" width="110">
              <template #default="{ row }">
                {{ row.installed_version || (row.loaded ? '已加载' : '-') }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="230" align="right">
              <template #default="{ row }">
                <div class="row-links">
                  <el-button
                    v-if="row.package"
                    link
                    type="primary"
                    @click="openInstall(row)"
                  >
                    {{ row.installed ? '更新' : '安装' }}
                  </el-button>
                  <el-button
                    v-if="!row.loaded"
                    link
                    type="primary"
                    :loading="busyItem === row.module"
                    @click="importMarketItem(row)"
                  >
                    引入
                  </el-button>
                  <el-button
                    v-if="row.pypi"
                    link
                    type="primary"
                    tag="a"
                    :href="row.pypi"
                    target="_blank"
                    rel="noopener"
                  >
                    PyPI
                  </el-button>
                  <el-button
                    v-if="row.installed_version"
                    link
                    type="danger"
                    :loading="busyItem === row.module"
                    @click="purgePackage(row)"
                  >
                    卸载
                  </el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>

          <div v-if="marketTotal > 0" class="table-pager">
            <el-pagination
              background
              :current-page="marketPage"
              :page-size="marketPageSize"
              :page-sizes="[10, 20, 50]"
              :total="marketTotal"
              layout="sizes, prev, pager, next"
              @current-change="changeMarketPage"
              @size-change="changeMarketPageSize"
            />
          </div>
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

    <el-dialog v-model="installDialog" title="安装第三方钩子包" width="560px">
      <el-form label-position="top">
        <el-form-item label="包名">
          <el-input
            v-model="installForm.package"
            placeholder="如 sapic-hook-cos，可带版本：sapic-hook-cos==1.0.0"
            @keyup.enter="submitInstall"
          />
        </el-form-item>
        <el-form-item label="模块名（可选）">
          <el-input
            v-model="installForm.module"
            placeholder="安装完成后要引入的模块，如 sapic_hook_cos"
          />
        </el-form-item>
        <el-form-item label="镜像地址（可选）">
          <el-input
            v-model="installForm.index_url"
            placeholder="https://pypi.tuna.tsinghua.edu.cn/simple"
          />
        </el-form-item>
        <el-form-item label="覆盖已安装版本">
          <el-switch v-model="installForm.upgrade" />
        </el-form-item>
      </el-form>

      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="安装会在服务端执行 pip，只安装可信来源的包；过程可能持续数十秒。"
      />
      <pre v-if="installLog" class="install-log" :class="{ 'is-error': !installResult }">{{
        installLog
      }}</pre>

      <template #footer>
        <el-button @click="installDialog = false">关闭</el-button>
        <el-button type="primary" :loading="installing" @click="submitInstall">
          开始安装
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
