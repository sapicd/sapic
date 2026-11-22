<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import { api, errorMessage } from '@/api/client'
import { t } from '@/i18n'
import { absoluteUrl, formatTime } from '@/utils/format'

//: 审核结果只在管理接口可见；这里默认打开「被拦截」，也是管理员最需要处理的队列。
const STATE_FILTERS = computed(() => [
  { label: t('adminReview.stateBlock'), value: 'block' },
  { label: t('adminReview.statePending'), value: 'pending' },
  { label: t('adminReview.statePass'), value: 'pass' },
  { label: t('adminReview.stateAll'), value: 'all' },
])

const state = ref('block')
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(15)
const loading = ref(false)
const busy = ref(false)
const selection = ref([])

let requestSeq = 0

async function load(target = page.value) {
  const seq = ++requestSeq
  loading.value = true
  try {
    const data = await api.get('/review', {
      query: { state: state.value, page: target, page_size: pageSize.value },
    })
    if (seq !== requestSeq) return
    items.value = data?.items || []
    total.value = Number(data?.total || 0)
    page.value = Number(data?.page || target)
    selection.value = []
  } catch (error) {
    if (seq === requestSeq) {
      ElMessage.error(errorMessage(error, t('adminReview.loadFailed')))
    }
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

watch(state, () => {
  page.value = 1
  load(1)
})

function onSelectionChange(rows) {
  selection.value = rows
}

async function decide(rows, action) {
  const shas = rows.map((row) => row.sha).filter(Boolean)
  if (!shas.length || busy.value) return
  busy.value = true
  try {
    const data = await api.post('/review/batch', { json: { action, shas } })
    ElMessage.success(t('adminReview.actionDone', { n: data?.affected || 0 }))
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, t('adminReview.actionFailed')))
  } finally {
    busy.value = false
  }
}

async function purge(rows) {
  if (!rows.length) return
  try {
    await ElMessageBox.confirm(
      t('adminReview.confirmPurge', { n: rows.length }),
      t('adminReview.purge'),
      { type: 'warning' },
    )
  } catch {
    return
  }
  await decide(rows, 'purge')
}

function stateLabel(value) {
  if (value === 'block') return t('adminReview.stateBlock')
  if (value === 'pass') return t('adminReview.statePass')
  return t('adminReview.statePending')
}

function stateType(value) {
  if (value === 'block') return 'danger'
  if (value === 'pass') return 'success'
  return 'warning'
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="page">
    <div class="page__header">
      <h2 class="page__title">{{ t('adminReview.title') }}</h2>
      <el-button :loading="loading" @click="load()">{{ t('common.refresh') }}</el-button>
    </div>
    <p class="hint">{{ t('adminReview.hint') }}</p>

    <el-card>
      <div class="review-toolbar">
        <el-select v-model="state" style="width: 160px">
          <el-option
            v-for="item in STATE_FILTERS"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <span class="review-selected">{{ t('adminReview.selected', { n: selection.length }) }}</span>
        <div class="review-toolbar__actions">
          <el-button
            :disabled="!selection.length || busy"
            :loading="busy"
            @click="decide(selection, 'approve')"
          >
            {{ t('adminReview.batchApprove') }}
          </el-button>
          <el-button
            type="danger"
            plain
            :disabled="!selection.length || busy"
            @click="purge(selection)"
          >
            {{ t('adminReview.batchPurge') }}
          </el-button>
        </div>
      </div>

      <el-table :data="items" row-key="sha" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="46" />
        <el-table-column :label="t('adminReview.image')" width="80">
          <template #default="{ row }">
            <el-image
              v-if="!row.is_video"
              :src="absoluteUrl(row.src)"
              :preview-src-list="[absoluteUrl(row.src)]"
              preview-teleported
              fit="cover"
              class="review-thumb"
            />
            <el-icon v-else size="20"><VideoCamera /></el-icon>
          </template>
        </el-table-column>
        <el-table-column :label="t('adminReview.filename')" min-width="180">
          <template #default="{ row }">
            <router-link :to="{ name: 'image-detail', params: { sha: row.sha } }">
              {{ row.title || row.filename || row.sha.slice(0, 12) }}
            </router-link>
          </template>
        </el-table-column>
        <el-table-column :label="t('adminReview.state')" width="100">
          <template #default="{ row }">
            <el-tag :type="stateType(row.review_state)" size="small" effect="light">
              {{ stateLabel(row.review_state) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('adminReview.note')" min-width="200">
          <template #default="{ row }">
            <span class="review-note">{{ row.review_note || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('adminReview.reviewedAt')" min-width="160">
          <template #default="{ row }">
            {{ row.reviewed_at ? formatTime(row.reviewed_at) : '-' }}
          </template>
        </el-table-column>
        <el-table-column :label="t('adminReview.actions')" width="180" align="left">
          <template #default="{ row }">
            <el-button
              v-if="row.review_state !== 'pass'"
              link
              type="primary"
              :disabled="busy"
              @click="decide([row], 'approve')"
            >
              {{ t('adminReview.approve') }}
            </el-button>
            <el-button
              v-if="row.review_state !== 'block'"
              link
              type="warning"
              :disabled="busy"
              @click="decide([row], 'block')"
            >
              {{ t('adminReview.blockAction') }}
            </el-button>
            <el-button link type="danger" :disabled="busy" @click="purge([row])">
              {{ t('adminReview.purge') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="review-pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[15, 30, 60]"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="load()"
          @size-change="load(1)"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.review-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.review-toolbar__actions {
  margin-left: auto;
}

.review-selected {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.review-thumb {
  width: 48px;
  height: 48px;
  border-radius: 4px;
}

.review-note {
  color: var(--el-text-color-regular);
  word-break: break-all;
}

.review-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
