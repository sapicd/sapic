<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { api, errorMessage } from '@/api/client'
import HookConfigForm from '@/components/hook/HookConfigForm.vue'
import { hookText } from '@/components/hook/text'
import { t } from '@/i18n'
import { formatTime } from '@/utils/format'

const router = useRouter()

//: 分类与市场状态都由后端 / 第三方数据给出，只做展示映射，不认识的值原样显示。
const CATALOGS = computed(() => ({
  upload: t('adminHooks.catalogUpload'),
  processor: t('adminHooks.catalogProcessor'),
  auth: t('adminHooks.catalogAuth'),
  mail: t('adminHooks.catalogMail'),
}))

const MARKET_STATUS = computed(() => ({
  stable: t('adminHooks.statusStable'),
  production: t('adminHooks.statusStable'),
  ga: t('adminHooks.statusStable'),
  beta: t('adminHooks.statusBeta'),
  rc: t('adminHooks.statusRc'),
  archive: t('adminHooks.statusArchived'),
}))

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
    ElMessage.error(errorMessage(error, t('adminHooks.loadListFailed')))
  } finally {
    loading.value = false
  }
}

async function loadConfigs() {
  try {
    const data = await api.get('/hooks/config')
    configs.value = data?.items || []
  } catch (error) {
    ElMessage.error(errorMessage(error, t('adminHooks.loadConfigFailed')))
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
    ElMessage.success(t('adminHooks.reloaded'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('adminHooks.reloadFailed')))
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
    ElMessage.warning(t('adminHooks.moduleRequired'))
    return
  }
  importing.value = true
  try {
    await api.post('/hooks/import', { json: { module } })
    importDialog.value = false
    await refresh()
    ElMessage.success(t('adminHooks.imported'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('adminHooks.importFailed')))
  } finally {
    importing.value = false
  }
}

//: 钩子可以给自己的 manifest 文案配 i18n 键；没配时按模块名兜底，最后才用原文。
function manifestText(row, field) {
  return hookText(row.name, field, row[field], row[`${field}_key`])
}

async function removeHook(row) {
  try {
    await ElMessageBox.confirm(
      t('adminHooks.removeConfirm', { name: row.name }),
      t('adminHooks.removeTitle'),
      { type: 'warning' },
    )
  } catch (error) {
    return
  }
  removing.value = row.name
  try {
    await api.del(`/hooks/import/${row.name}`)
    await refresh()
    ElMessage.success(t('adminHooks.removed'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('adminHooks.removeFailed')))
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
    ElMessage.success(row.enabled ? t('adminHooks.enabled') : t('adminHooks.disabled'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('adminHooks.actionFailed')))
  } finally {
    toggling.value = ''
  }
}

async function saveConfig(item, values) {
  saving.value = item.name
  try {
    const data = await api.put(`/hooks/config/${item.name}`, { json: values })
    item.values = data?.values || values
    ElMessage.success(t('adminHooks.configSaved'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('adminHooks.saveFailed')))
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
      ElMessage.success(data?.toast?.text || t('adminHooks.checkPassed'))
    } else {
      ElMessage.error(data?.message || t('adminHooks.checkFailed'))
    }
  } catch (error) {
    ElMessage.error(errorMessage(error, t('adminHooks.checkError')))
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
    marketError.value = errorMessage(error, t('adminHooks.marketLoadFailed'))
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
    ElMessage.warning(t('adminHooks.packageRequired'))
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
      ElMessage.success(t('adminHooks.installed'))
      installDialog.value = false
      await Promise.all([refresh(), loadMarket()])
    }
  } catch (error) {
    installResult.value = false
    installLog.value = errorMessage(error, t('adminHooks.installFailed'))
  } finally {
    installing.value = false
  }
}

async function importMarketItem(item) {
  busyItem.value = item.module
  try {
    await api.post('/hooks/import', { json: { module: item.module } })
    ElMessage.success(t('adminHooks.marketImported'))
    await Promise.all([refresh(), loadMarket()])
  } catch (error) {
    ElMessage.error(errorMessage(error, t('adminHooks.marketImportFailed')))
  } finally {
    busyItem.value = ''
  }
}

async function purgePackage(item) {
  try {
    await ElMessageBox.confirm(
      t('adminHooks.purgeConfirm', {
        name: item.name,
        dir: marketMeta.value.storage_dir || t('adminHooks.packageDir'),
      }),
      t('adminHooks.purgeTitle'),
      { type: 'warning' },
    )
  } catch (error) {
    return
  }
  busyItem.value = item.module
  try {
    await api.del(`/hooks/import/${item.module}`, { query: { purge: 1 } })
    ElMessage.success(t('adminHooks.purged'))
    await Promise.all([refresh(), loadMarket()])
  } catch (error) {
    ElMessage.error(errorMessage(error, t('adminHooks.purgeFailed')))
  } finally {
    busyItem.value = ''
  }
}

onMounted(refresh)
</script>

<template>
  <div v-loading="loading" class="page">
    <div class="page__header">
      <h2 class="page__title">{{ t('admin.hooks') }}</h2>
      <el-button @click="refresh">{{ t('common.refresh') }}</el-button>
    </div>

    <el-card>
      <el-tabs v-model="tab">
        <el-tab-pane :label="t('adminHooks.tabHooks')" name="hooks">
          <div class="toolbar hook-toolbar">
            <el-button type="primary" :loading="reloading" @click="reloadHooks">
              {{ t('adminHooks.reload') }}
            </el-button>
            <el-button @click="openImport">{{ t('adminHooks.importHook') }}</el-button>
            <span class="toolbar__meta">
              {{ t('adminHooks.summary', { total: manifests.length, enabled: enabledCount }) }}
            </span>
          </div>

          <el-empty
            v-if="!manifests.length"
            :description="t('adminHooks.emptyHooks')"
            :image-size="60"
          />
          <el-table v-else :data="manifests" row-key="name" style="width: 100%">
            <el-table-column :label="t('common.name')" min-width="150">
              <template #default="{ row }">
                <span :title="manifestText(row, 'title')">{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="version" :label="t('adminHooks.version')" width="90" />
            <el-table-column
              prop="author"
              :label="t('adminHooks.author')"
              width="130"
              show-overflow-tooltip
            />
            <el-table-column :label="t('adminHooks.description')" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                {{ manifestText(row, 'description') }}
              </template>
            </el-table-column>
            <el-table-column :label="t('adminHooks.type')" width="90">
              <template #default="{ row }">
                {{ CATALOGS[row.catalog] || row.catalog || t('adminHooks.catalogOther') }}
              </template>
            </el-table-column>
            <el-table-column :label="t('adminHooks.source')" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="row.family === 'third' ? 'warning' : 'info'" effect="plain">
                  {{ row.family === 'third' ? t('adminHooks.sourceThird') : t('adminHooks.sourceLocal') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('common.status')" width="100">
              <template #default="{ row }">
                <el-switch
                  :model-value="row.enabled"
                  :loading="toggling === row.name"
                  :active-text="t('adminHooks.switchOn')"
                  :inactive-text="t('adminHooks.switchOff')"
                  inline-prompt
                  @change="(value) => toggleHook(row, value)"
                />
              </template>
            </el-table-column>
            <el-table-column :label="t('common.actions')" width="90" align="right">
              <template #default="{ row }">
                <el-button
                  v-if="row.family === 'third'"
                  link
                  type="danger"
                  :loading="removing === row.name"
                  @click="removeHook(row)"
                >
                  {{ t('adminHooks.remove') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane :label="t('adminHooks.tabConfig')" name="config">
          <p class="hint">{{ t('adminHooks.configHint') }}</p>

          <el-alert
            v-if="uploadConfigs.length"
            type="info"
            :closable="false"
            show-icon
            style="margin-bottom: 16px"
          >
            <template #title>
              {{
                t('adminHooks.storageConfigAlert', {
                  names: uploadConfigs.map((item) => manifestText(item, 'title')).join(' / '),
                })
              }}
            </template>
            <el-button link type="primary" @click="router.push({ name: 'admin-backends' })">
              {{ t('adminHooks.goBackends') }}
            </el-button>
          </el-alert>

          <el-empty
            v-if="!otherConfigs.length"
            :description="t('adminHooks.emptyConfig')"
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

        <el-tab-pane :label="t('adminHooks.tabMarket')" name="market">
          <el-alert
            v-if="!marketMeta.configured"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 12px"
            :title="t('adminHooks.marketNotConfiguredTitle')"
            :description="t('adminHooks.marketNotConfiguredDesc')"
          />

          <div class="toolbar hook-toolbar">
            <el-button :loading="marketLoading" @click="refreshMarket">
              {{ t('adminHooks.refreshMarket') }}
            </el-button>
            <el-button @click="openCustomInstall">{{ t('adminHooks.manualInstall') }}</el-button>
            <span class="toolbar__meta">
              {{
                marketMeta.updated_at
                  ? t('adminHooks.marketSummaryCached', {
                      total: marketTotal,
                      time: formatTime(marketMeta.updated_at),
                    })
                  : t('adminHooks.marketSummary', { total: marketTotal })
              }}
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
            {{ t('adminHooks.marketHintBefore') }}<code>appversion: "2.x"</code>{{
              t('adminHooks.marketHintMiddle')
            }}<code>{{ marketMeta.storage_dir || t('adminHooks.packageDir') }}</code
            >{{ t('adminHooks.marketHintAfter') }}
          </p>

          <el-empty
            v-if="!marketLoading && !marketItems.length"
            :description="t('adminHooks.emptyMarket')"
            :image-size="60"
          />
          <el-table
            v-else
            v-loading="marketLoading"
            :data="marketItems"
            row-key="module"
            style="width: 100%"
          >
            <el-table-column :label="t('common.name')" min-width="150">
              <template #default="{ row }">
                <div class="market-name">
                  <span>{{ row.name }}</span>
                  <el-tag v-if="row.loaded" size="small" type="success" effect="plain">
                    {{ t('adminHooks.loaded') }}
                  </el-tag>
                </div>
                <span class="market-module">{{ row.module }}</span>
              </template>
            </el-table-column>
            <el-table-column
              prop="description"
              :label="t('adminHooks.description')"
              min-width="200"
              show-overflow-tooltip
            />
            <el-table-column :label="t('adminHooks.author')" width="120" show-overflow-tooltip>
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
            <el-table-column :label="t('common.status')" width="100">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">
                  {{ MARKET_STATUS[row.status] || row.status || t('common.unknown') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('adminHooks.columnInstalledVersion')" width="110">
              <template #default="{ row }">
                {{
                  row.installed_version ||
                  row.loaded_version ||
                  (row.loaded ? t('adminHooks.loaded') : '-')
                }}
              </template>
            </el-table-column>
            <el-table-column :label="t('common.actions')" width="230" align="right">
              <template #default="{ row }">
                <div class="row-links">
                  <el-button
                    v-if="row.package"
                    link
                    type="primary"
                    @click="openInstall(row)"
                  >
                    {{ row.installed ? t('adminHooks.update') : t('adminHooks.install') }}
                  </el-button>
                  <el-button
                    v-if="!row.loaded"
                    link
                    type="primary"
                    :loading="busyItem === row.module"
                    @click="importMarketItem(row)"
                  >
                    {{ t('adminHooks.importAction') }}
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
                    {{ t('adminHooks.uninstall') }}
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

    <el-dialog v-model="importDialog" :title="t('adminHooks.importHook')" width="480px">
      <el-form label-position="top">
        <el-form-item :label="t('adminHooks.module')">
          <el-input
            v-model="importModule"
            :placeholder="t('adminHooks.installHint')"
            @keyup.enter="importHook"
          />
        </el-form-item>
      </el-form>
      <p class="hint">{{ t('adminHooks.importHint') }}</p>
      <template #footer>
        <el-button @click="importDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="importing" @click="importHook">
          {{ t('adminHooks.import') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="installDialog"
      :title="t('adminHooks.installPackage')"
      width="560px"
    >
      <el-form label-position="top">
        <el-form-item :label="t('adminHooks.packageLabel')">
          <el-input
            v-model="installForm.package"
            :placeholder="t('adminHooks.packagePlaceholder')"
            @keyup.enter="submitInstall"
          />
        </el-form-item>
        <el-form-item :label="t('adminHooks.moduleOptional')">
          <el-input
            v-model="installForm.module"
            :placeholder="t('adminHooks.moduleOptionalPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('adminHooks.indexUrl')">
          <el-input
            v-model="installForm.index_url"
            :placeholder="t('adminHooks.indexUrlPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('adminHooks.upgrade')">
          <el-switch v-model="installForm.upgrade" />
        </el-form-item>
      </el-form>

      <el-alert
        type="warning"
        :closable="false"
        show-icon
        :title="t('adminHooks.installWarning')"
      />
      <pre v-if="installLog" class="install-log" :class="{ 'is-error': !installResult }">{{
        installLog
      }}</pre>

      <template #footer>
        <el-button @click="installDialog = false">{{ t('common.close') }}</el-button>
        <el-button type="primary" :loading="installing" @click="submitInstall">
          {{ t('adminHooks.startInstall') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
