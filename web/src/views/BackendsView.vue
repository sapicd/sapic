<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { api, errorMessage } from '@/api/client'

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
    ElMessage.error(errorMessage(error, '加载存储后端失败'))
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
    ElMessage.warning('请选择存储驱动')
    return
  }
  if (form.visibility === 'private' && !driverPrivateReadable.value) {
    ElMessage.warning('当前驱动不支持私有读，请改用公开直链或换驱动')
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
    ElMessage.success(editing.value ? '后端已更新' : '后端已创建')
  } catch (error) {
    ElMessage.error(errorMessage(error, '保存失败'))
  } finally {
    saving.value = false
  }
}

async function runPing(hookName, values) {
  const data = await api.post(`/hooks/${hookName}/actions/ping`, {
    json: { values },
  })
  if (data?.code === 0) {
    ElMessage.success(data?.toast?.text || '检测通过')
  } else {
    ElMessage.error(data?.message || '检测未通过')
  }
}

async function ping(row) {
  checking.value = row.id
  try {
    await runPing(row.hook_name, row.config)
  } catch (error) {
    ElMessage.error(errorMessage(error, '检测失败'))
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
    ElMessage.error(errorMessage(error, '检测失败'))
  } finally {
    checkingForm.value = false
  }
}

async function toggle(row, enabled) {
  toggling.value = row.id
  try {
    const data = await api.patch(`/backends/${row.id}`, { json: { enabled } })
    items.value = data?.items || items.value
    ElMessage.success(enabled ? '已启用' : '已禁用')
  } catch (error) {
    ElMessage.error(errorMessage(error, '操作失败'))
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
    ElMessage.error(errorMessage(error, '调整优先级失败'))
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除存储后端「${row.name}」吗？仍有图片副本时会被拒绝。`,
      '删除后端',
      { type: 'warning', confirmButtonText: '删除' },
    )
  } catch (error) {
    return
  }
  try {
    const data = await api.del(`/backends/${row.id}`)
    items.value = data?.items || items.value
    ElMessage.success('后端已删除')
  } catch (error) {
    ElMessage.error(errorMessage(error, '删除失败'))
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="page">
    <div class="page__header">
      <h2 class="page__title">存储后端</h2>
      <div>
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">新增后端</el-button>
      </div>
    </div>

    <el-card>
      <p class="hint">
        上传同步写入「优先级最小」的启用后端，其余启用的后端在后台异步补副本（站点设置里可关闭），
        直链与读取都按优先级从高到低选副本；已有图片按副本所在后端读取，所以仍有副本的后端不能删除或禁用。
        启用存储钩子后会自动出现对应后端，<strong>驱动凭据只在这里填写</strong>（同一驱动可建多个后端各自一套配置）。
        后端为<strong>公开</strong>时公开图直接用直链，为<strong>私有</strong>时（七牛 / 又拍 / GitHub 私有仓库，
        或本地目录）所有图片都经 <code>/raw</code> 由服务端签名读取，桶始终不对外。
      </p>

      <el-table :data="items" size="small">
        <el-table-column label="名称" min-width="140">
          <template #default="{ row }">
            <span>{{ row.name }}</span>
            <el-tag v-if="row.in_use" size="small" type="success" effect="plain" style="margin-left: 6px">
              当前写入
            </el-tag>
            <el-tag
              v-if="!row.configured"
              size="small"
              type="warning"
              effect="plain"
              style="margin-left: 6px"
            >
              待配置
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="驱动" min-width="150">
          <template #default="{ row }">
            <span :title="row.hook_name">{{ row.title }}</span>
            <div class="hint">{{ row.hook_name }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="90" />
        <el-table-column label="访问方式" width="100">
          <template #default="{ row }">
            <el-tooltip
              :content="
                row.visibility === 'private'
                  ? '桶私有读，所有访问经 /raw 由服务端签发读地址后转发'
                  : '桶公有读，公开图直接使用驱动返回的直链'
              "
            >
              <el-tag
                size="small"
                effect="plain"
                :type="row.visibility === 'private' ? 'warning' : 'info'"
              >
                {{ row.visibility === 'private' ? '私有' : '公开' }}
              </el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="副本" width="80">
          <template #default="{ row }">
            <el-tooltip content="仅统计写入成功的副本" placement="top">
              <span>{{ row.replicas }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-switch
              :model-value="row.enabled"
              :loading="toggling === row.id"
              active-text="启用"
              inactive-text="禁用"
              inline-prompt
              @change="(value) => toggle(row, value)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" align="right">
          <template #default="{ row }">
            <el-button link size="small" :disabled="!row.enabled" @click="move(row, -1)">
              上移
            </el-button>
            <el-button link size="small" :disabled="!row.enabled" @click="move(row, 1)">
              下移
            </el-button>
            <el-button
              link
              size="small"
              :loading="checking === row.id"
              @click="ping(row)"
            >
              检查
            </el-button>
            <el-button link type="primary" size="small" @click="openEdit(row)">配置</el-button>
            <el-button link type="danger" size="small" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="还没有存储后端" :image-size="60" />
        </template>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialog"
      :title="editing ? '编辑存储后端' : '新增存储后端'"
      width="520px"
    >
      <el-form label-position="top">
        <el-form-item label="驱动">
          <el-select v-model="form.hook_name" :disabled="editing" style="width: 100%">
            <el-option
              v-for="driver in drivers"
              :key="driver.name"
              :label="`${driver.title}（${driver.name}）`"
              :value="driver.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="留空则按驱动名自动生成" />
        </el-form-item>
        <el-form-item label="访问方式">
          <el-select v-model="form.visibility" style="width: 100%">
            <el-option label="公开直链（公有读桶 + CDN）" value="public" />
            <el-option
              label="私有代理（私有桶，经 /raw 转发）"
              value="private"
              :disabled="!driverPrivateReadable"
            />
          </el-select>
          <div class="hint">
            公开：公开图直接使用驱动返回的直链（需桶公有读、可配域名）。
            私有：桶保持私有读，任何访问都先经 sapic 鉴权，再由服务端凭驱动签发的临时读地址转发。
            <template v-if="!driverPrivateReadable">
              当前驱动未实现 upimg_url，只能作为公开后端。
            </template>
          </div>
        </el-form-item>
        <el-form-item label="优先级（越小越先写入）">
          <el-input-number
            v-model="form.priority"
            :min="1"
            :step="10"
            controls-position="right"
            placeholder="留空自动排到最后"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item
          v-for="field in fields"
          :key="field.key"
          :label="field.label || field.key"
          :required="field.required"
        >
          <el-input
            v-model="form.config[field.key]"
            :type="field.type === 'password' ? 'password' : 'text'"
            :show-password="field.type === 'password'"
            :placeholder="field.placeholder"
          />
          <div v-if="field.help" class="hint">{{ field.help }}</div>
        </el-form-item>
      </el-form>
      <p class="hint">
        带 * 的字段是驱动必需项，保存时会校验；「检查」会用当前表单的值探测一次存储桶。
      </p>
      <template #footer>
        <el-button :loading="checkingForm" @click="pingForm">检查</el-button>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
