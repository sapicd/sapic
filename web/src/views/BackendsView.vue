<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { api, errorMessage } from '@/api/client'
import { hookText, nodeText } from '@/components/hook/text'
import { t } from '@/i18n'

const items = ref([])
const drivers = ref([])
const loading = ref(false)
const saving = ref(false)
const toggling = ref(0)
const checking = ref(0)
const checkingForm = ref(false)

const dialog = ref(false)
const form = reactive({
  id: null,
  name: '',
  hook_name: '',
  priority: null,
  visibility: 'public',
  config: {},
})

const editing = computed(() => form.id !== null)
const fields = computed(
  () => drivers.value.find((item) => item.name === form.hook_name)?.fields || [],
)
//: 驱动没有 upimg_url 时只能当公开后端用，后端保存时也会拒绝。
const driverPrivateReadable = computed(
  () => drivers.value.find((item) => item.name === form.hook_name)?.private_readable !== false,
)

async function load() {
  loading.value = true
  try {
    const data = await api.get('/backends')
    items.value = data?.items || []
    drivers.value = data?.drivers || []
  } catch (error) {
    ElMessage.error(errorMessage(error, t('backends.loadFailed')))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, {
    id: null,
    name: '',
    hook_name: drivers.value[0]?.name || '',
    priority: null,
    visibility: 'public',
    config: {},
  })
  dialog.value = true
}

function openEdit(row) {
  Object.assign(form, {
    id: row.id,
    name: row.name,
    hook_name: row.hook_name,
    priority: row.priority,
    visibility: row.visibility || 'public',
    config: { ...(row.config || {}) },
  })
  dialog.value = true
}

async function save() {
  if (!form.hook_name) {
    ElMessage.warning(t('backends.driverRequired'))
    return
  }
  if (form.visibility === 'private' && !driverPrivateReadable.value) {
    ElMessage.warning(t('backends.privateUnsupported'))
    return
  }
  const payload = {
    name: form.name.trim(),
    visibility: form.visibility,
    config: form.config,
    priority: form.priority === null ? undefined : Number(form.priority),
  }
  saving.value = true
  try {
    const data = editing.value
      ? await api.patch(`/backends/${form.id}`, { json: payload })
      : await api.post('/backends', { json: { ...payload, hook_name: form.hook_name } })
    items.value = data?.items || items.value
    drivers.value = data?.drivers || drivers.value
    dialog.value = false
    ElMessage.success(editing.value ? t('backends.updated') : t('backends.created'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('albums.saveFailed')))
  } finally {
    saving.value = false
  }
}

async function runPing(hookName, values) {
  const data = await api.post(`/hooks/${hookName}/actions/ping`, {
    json: { values },
  })
  if (data?.code === 0) {
    ElMessage.success(data?.toast?.text || t('backends.checkPassed'))
  } else {
    ElMessage.error(data?.message || t('backends.checkFailed'))
  }
}

async function ping(row) {
  checking.value = row.id
  try {
    await runPing(row.hook_name, row.config)
  } catch (error) {
    ElMessage.error(errorMessage(error, t('backends.checkError')))
  } finally {
    checking.value = 0
  }
}

async function pingForm() {
  if (!form.hook_name) return
  checkingForm.value = true
  try {
    await runPing(form.hook_name, form.config)
  } catch (error) {
    ElMessage.error(errorMessage(error, t('backends.checkError')))
  } finally {
    checkingForm.value = false
  }
}

async function toggle(row, enabled) {
  toggling.value = row.id
  try {
    const data = await api.patch(`/backends/${row.id}`, { json: { enabled } })
    items.value = data?.items || items.value
    ElMessage.success(enabled ? t('backends.toggledOn') : t('backends.toggledOff'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('backends.actionFailed')))
  } finally {
    toggling.value = 0
  }
}

async function move(row, step) {
  const enabledRows = items.value.filter((item) => item.enabled)
  const index = enabledRows.findIndex((item) => item.id === row.id)
  const target = enabledRows[index + step]
  if (!target) return
  try {
    await api.patch(`/backends/${row.id}`, { json: { priority: target.priority } })
    const data = await api.patch(`/backends/${target.id}`, {
      json: { priority: row.priority },
    })
    items.value = data?.items || items.value
  } catch (error) {
    ElMessage.error(errorMessage(error, t('backends.priorityFailed')))
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      t('backends.deleteConfirm', { name: row.name }),
      t('backends.deleteTitle'),
      { type: 'warning', confirmButtonText: t('common.delete') },
    )
  } catch (error) {
    return
  }
  try {
    const data = await api.del(`/backends/${row.id}`)
    items.value = data?.items || items.value
    ElMessage.success(t('backends.deleted'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('backends.deleteFailed')))
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="page">
    <div class="page__header">
      <h2 class="page__title">{{ t('backends.title') }}</h2>
      <div>
        <el-button @click="load">{{ t('common.refresh') }}</el-button>
        <el-button type="primary" @click="openCreate">{{ t('backends.createTitle') }}</el-button>
      </div>
    </div>

    <el-card>
      <p class="hint">
        {{ t('backends.intro') }}
      </p>

      <el-table :data="items" size="small">
        <el-table-column :label="t('backends.name')" min-width="140">
          <template #default="{ row }">
            <span>{{ row.name }}</span>
            <el-tag v-if="row.in_use" size="small" type="success" effect="plain" style="margin-left: 6px">
              {{ t('backends.currentWrite') }}
            </el-tag>
            <el-tag
              v-if="!row.configured"
              size="small"
              type="warning"
              effect="plain"
              style="margin-left: 6px"
            >
              {{ t('backends.needConfig') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('backends.driver')" min-width="150">
          <template #default="{ row }">
            <span :title="row.hook_name">
              {{ hookText(row.hook_name, 'title', row.title, row.title_key) }}
            </span>
            <div class="hint">{{ row.hook_name }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="priority" :label="t('backends.priority')" width="90" />
        <el-table-column :label="t('backends.accessLabel')" width="100">
          <template #default="{ row }">
            <el-tooltip
              :content="
                row.visibility === 'private'
                  ? t('backends.privateAccessHint')
                  : t('backends.publicAccessHint')
              "
            >
              <el-tag
                size="small"
                effect="plain"
                :type="row.visibility === 'private' ? 'warning' : 'info'"
              >
                {{ row.visibility === 'private' ? t('images.private') : t('images.public') }}
              </el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column :label="t('backends.replicas')" width="80">
          <template #default="{ row }">
            <el-tooltip :content="t('backends.replicaTooltip')" placement="top">
              <span>{{ row.replicas }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.status')" width="100">
          <template #default="{ row }">
            <el-switch
              :model-value="row.enabled"
              :loading="toggling === row.id"
              :active-text="t('backends.enable')"
              :inactive-text="t('backends.disable')"
              inline-prompt
              @change="(value) => toggle(row, value)"
            />
          </template>
        </el-table-column>
        <el-table-column :label="t('common.actions')" width="260" align="right">
          <template #default="{ row }">
            <el-button link size="small" :disabled="!row.enabled" @click="move(row, -1)">
              {{ t('backends.moveUp') }}
            </el-button>
            <el-button link size="small" :disabled="!row.enabled" @click="move(row, 1)">
              {{ t('backends.moveDown') }}
            </el-button>
            <el-button
              link
              size="small"
              :loading="checking === row.id"
              @click="ping(row)"
            >
              {{ t('backends.check') }}
            </el-button>
            <el-button link type="primary" size="small" @click="openEdit(row)">{{ t('backends.config') }}</el-button>
            <el-button link type="danger" size="small" @click="remove(row)">{{ t('common.delete') }}</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :description="t('backends.empty')" :image-size="60" />
        </template>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialog"
      :title="editing ? t('backends.editTitle') : t('backends.createTitle')"
      width="520px"
    >
      <el-form label-position="top">
        <el-form-item :label="t('backends.driverLabel')">
          <el-select v-model="form.hook_name" :disabled="editing" style="width: 100%">
            <el-option
              v-for="driver in drivers"
              :key="driver.name"
              :label="`${hookText(driver.name, 'title', driver.title, driver.title_key)} (${driver.name})`"
              :value="driver.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('backends.name')">
          <el-input v-model="form.name" :placeholder="t('backends.namePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('backends.accessLabel')">
          <el-select v-model="form.visibility" style="width: 100%">
            <el-option :label="t('backends.accessPublic')" value="public" />
            <el-option
              :label="t('backends.accessPrivate')"
              value="private"
              :disabled="!driverPrivateReadable"
            />
          </el-select>
          <div class="hint">
            {{ t('backends.accessPublicHint') }}
            {{ t('backends.accessPrivateHint') }}
            <template v-if="!driverPrivateReadable">
              {{ t('backends.noUpimgUrl') }}
            </template>
          </div>
        </el-form-item>
        <el-form-item :label="t('backends.priorityLabel')">
          <el-input-number
            v-model="form.priority"
            :min="1"
            :step="10"
            controls-position="right"
            :placeholder="t('backends.priorityPlaceholder')"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item
          v-for="field in fields"
          :key="field.key"
          :label="nodeText(field, 'label', form.hook_name) || field.key"
          :required="field.required"
        >
          <el-input
            v-model="form.config[field.key]"
            :type="field.type === 'password' ? 'password' : 'text'"
            :show-password="field.type === 'password'"
            :placeholder="nodeText(field, 'placeholder', form.hook_name)"
          />
          <div v-if="field.help || field.help_key" class="hint">
            {{ nodeText(field, 'help', form.hook_name) }}
          </div>
        </el-form-item>
      </el-form>
      <p class="hint">
        {{ t('backends.formHint') }}
      </p>
      <template #footer>
        <el-button :loading="checkingForm" @click="pingForm">{{ t('backends.check') }}</el-button>
        <el-button @click="dialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="save">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>
