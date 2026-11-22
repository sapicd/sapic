<script setup>
import { computed, onMounted, ref } from 'vue'

import { api, errorMessage } from '@/api/client'
import { t } from '@/i18n'
import { formatTime } from '@/utils/format'

//: 角色标签随语言切换，用 computed 包一层。
const ROLE_TYPE = { leader: 'success', standby: 'warning', disabled: 'info' }

const status = ref(null)
const loading = ref(false)
const running = ref('')

const roleMeta = computed(() => {
  const role = status.value?.role || 'disabled'
  return {
    type: ROLE_TYPE[role] || 'info',
    label: t(`adminScheduler.role_${role}`),
  }
})

const roleHint = computed(() => {
  const role = status.value?.role
  if (role === 'standby') return t('adminScheduler.standbyHint')
  if (role === 'disabled') return t('adminScheduler.disabledHint')
  return ''
})

function intervalText(seconds) {
  const value = Number(seconds || 0)
  if (!value) return '-'
  if (value % 3600 === 0) return t('adminScheduler.hours', { n: value / 3600 })
  if (value % 60 === 0) return t('adminScheduler.minutes', { n: value / 60 })
  return t('adminScheduler.seconds', { n: value })
}

//: 后端返回的 reason 是稳定的英文枚举，这里映射到文案键。
const DEMO_REASONS = {
  rotated: 'rotated',
  'already current': 'alreadyCurrent',
  'user not found': 'userNotFound',
  'admin account': 'admin',
  'not configured': 'notConfigured',
  disabled: 'disabled',
  'not due': 'notDue',
  error: 'error',
}

function demoText(reason) {
  return t(`adminScheduler.demo.${DEMO_REASONS[reason] || 'error'}`)
}

function resultText(job) {
  const last = job.last_run
  if (!last) return t('adminScheduler.never')
  if (!last.ok) return t('adminScheduler.failed')
  const result = last.result || {}
  if (job.id === 'purge_expired') {
    return t('adminScheduler.purged', { n: result.removed ?? 0 })
  }
  if (job.id === 'demo_rotate') {
    return demoText(result.reason)
  }
  return t('adminScheduler.scanned', {
    scanned: result.scanned ?? 0,
    blocked: result.blocked ?? 0,
    failed: result.failed ?? 0,
  })
}

const rows = computed(() =>
  (status.value?.jobs || []).map((job) => ({
    ...job,
    title: t(`adminScheduler.jobs.${job.id}`),
    intervalText: intervalText(job.interval),
    nextText: job.next_run_at ? formatTime(job.next_run_at) : '-',
    lastText: job.last_run?.at ? formatTime(job.last_run.at) : '-',
    resultText: resultText(job),
  })),
)

async function load() {
  loading.value = true
  try {
    status.value = await api.get('/scheduler')
  } catch (error) {
    ElMessage.error(errorMessage(error, t('adminScheduler.loadFailed')))
  } finally {
    loading.value = false
  }
}

async function runNow(row) {
  running.value = row.id
  try {
    const data = await api.post(`/scheduler/run/${row.id}`)
    if (row.id === 'purge_expired') {
      ElMessage.success(t('adminScheduler.purged', { n: data?.removed ?? 0 }))
    } else if (row.id === 'demo_rotate') {
      ElMessage.success(demoText(data?.demo?.reason))
    } else {
      const review = data?.review || {}
      ElMessage.success(
        t('adminScheduler.scanned', {
          scanned: review.scanned ?? 0,
          blocked: review.blocked ?? 0,
          failed: review.failed ?? 0,
        }),
      )
    }
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, t('adminScheduler.runFailed')))
  } finally {
    running.value = ''
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="page">
    <div class="page__header">
      <h2 class="page__title">{{ t('adminScheduler.title') }}</h2>
      <el-button @click="load">{{ t('common.refresh') }}</el-button>
    </div>

    <el-card>
      <p class="hint">{{ t('adminScheduler.intro') }}</p>

      <el-descriptions :column="3" border size="small">
        <el-descriptions-item :label="t('adminScheduler.state')">
          <el-tag :type="roleMeta.type" size="small" effect="plain">{{ roleMeta.label }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('adminScheduler.pid')">
          {{ status?.pid ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('adminScheduler.lockFile')">
          <code>{{ status?.lock || '-' }}</code>
        </el-descriptions-item>
      </el-descriptions>

      <el-alert
        v-if="roleHint"
        :title="roleHint"
        :type="status?.role === 'disabled' ? 'info' : 'warning'"
        :closable="false"
        show-icon
        style="margin-top: 12px"
      />

      <el-table :data="rows" size="small" style="margin-top: 12px">
        <el-table-column :label="t('adminScheduler.job')" min-width="160">
          <template #default="{ row }">
            <div>{{ row.title }}</div>
            <div class="hint" style="margin: 0"><code>{{ row.id }}</code></div>
          </template>
        </el-table-column>
        <el-table-column :label="t('adminScheduler.interval')" width="110">
          <template #default="{ row }">{{ row.intervalText }}</template>
        </el-table-column>
        <el-table-column :label="t('adminScheduler.nextRun')" min-width="150">
          <template #default="{ row }">{{ row.nextText }}</template>
        </el-table-column>
        <el-table-column :label="t('adminScheduler.lastRun')" min-width="150">
          <template #default="{ row }">{{ row.lastText }}</template>
        </el-table-column>
        <el-table-column :label="t('adminScheduler.result')" min-width="200">
          <template #default="{ row }">
            <span :class="{ 'scheduler-result--failed': row.last_run && !row.last_run.ok }">
              {{ row.resultText }}
            </span>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.actions')" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              :loading="running === row.id"
              :disabled="!!running && running !== row.id"
              @click="runNow(row)"
            >
              {{ t('adminScheduler.runNow') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <p class="hint" style="margin-bottom: 0">{{ t('adminScheduler.intervalHint') }}</p>
    </el-card>
  </div>
</template>

<style scoped>
.scheduler-result--failed {
  color: var(--el-color-danger);
}
</style>
