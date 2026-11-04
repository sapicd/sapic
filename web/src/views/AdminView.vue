<script setup>
import { onMounted, ref } from 'vue'

import { api, errorMessage } from '@/api/client'
import HookSlot from '@/components/hook/HookSlot.vue'
import { useSiteStore } from '@/stores/site'

const site = useSiteStore()

const loading = ref(false)
const form = ref({})
const editable = ref([])
const tab = ref('site')
const saving = ref(false)

async function loadSettings() {
  loading.value = true
  try {
    const data = await api.get('/settings')
    form.value = data?.items || {}
    editable.value = data?.editable || []
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载站点设置失败'))
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  const payload = {}
  editable.value.forEach((key) => {
    payload[key] = form.value[key]
  })
  saving.value = true
  try {
    const data = await api.put('/settings', { json: payload })
    form.value = data?.items || form.value
    await site.load()
    ElMessage.success('设置已保存')
  } catch (error) {
    ElMessage.error(errorMessage(error, '保存失败'))
  } finally {
    saving.value = false
  }
}

onMounted(loadSettings)
</script>

<template>
  <div v-loading="loading" class="page">
    <div class="page__header">
      <h2 class="page__title">站点设置</h2>
      <el-button @click="loadSettings">刷新</el-button>
    </div>

    <el-card>
      <template #header>
        <div class="card-header">
          <span>站点设置</span>
          <el-button type="primary" size="small" :loading="saving" @click="saveSettings">
            保存
          </el-button>
        </div>
      </template>

      <el-tabs v-model="tab">
        <el-tab-pane label="站点" name="site">
          <el-form label-width="120px">
            <el-form-item label="站点名称">
              <el-input v-model="form.site_name" maxlength="64" />
            </el-form-item>
            <el-form-item label="站点关键词">
              <el-input v-model="form.site_keywords" placeholder="SEO 关键词，逗号分隔" />
            </el-form-item>
            <el-form-item label="站点描述">
              <el-input v-model="form.site_description" type="textarea" :rows="2" />
            </el-form-item>
            <el-form-item label="Logo 地址">
              <el-input v-model="form.site_logo" placeholder="留空使用内置 logo" />
            </el-form-item>
            <el-form-item label="背景图">
              <el-input v-model="form.site_background" placeholder="留空使用内置背景" />
            </el-form-item>
            <el-form-item label="移动端背景">
              <el-input v-model="form.site_background_mobile" placeholder="留空复用背景图" />
            </el-form-item>
            <el-form-item label="背景遮罩">
              <el-slider
                v-model="form.site_background_opacity"
                :min="0"
                :max="1"
                :step="0.1"
                show-input
              />
            </el-form-item>
            <el-form-item label="备案号">
              <el-input v-model="form.site_icp" placeholder="如 京ICP备xxxxxxx号-1" />
            </el-form-item>
            <el-form-item label="页脚版权">
              <el-input v-model="form.site_footer" placeholder="SaintIC. All rights reserved." />
            </el-form-item>
            <el-form-item label="全站公告">
              <el-input v-model="form.site_announcement" type="textarea" :rows="3" />
            </el-form-item>
            <el-form-item label="关于本站">
              <el-input v-model="form.site_about" type="textarea" :rows="3" />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="上传" name="upload">
          <el-form label-width="120px">
            <el-form-item label="匿名上传">
              <el-switch v-model="form.allow_anonymous_upload" />
            </el-form-item>
            <el-form-item label="上传提示">
              <el-input
                v-model="form.upload_notice"
                type="textarea"
                :rows="2"
                placeholder="显示在首页上传区，留空使用默认文案"
              />
            </el-form-item>
            <el-form-item label="允许后缀">
              <el-input
                v-model="form.upload_allowed_ext"
                placeholder="jpg,png,gif,webp,mp4"
              />
            </el-form-item>
            <el-form-item label="大小限制">
              <el-input-number v-model="form.upload_max_size" :min="1" :max="1024" />
              <span class="form-suffix">MB</span>
            </el-form-item>
            <el-form-item label="数量限制">
              <el-input-number v-model="form.upload_count_limit" :min="1" :max="100" />
              <span class="form-suffix">个 / 次</span>
            </el-form-item>
            <el-form-item label="允许视频">
              <el-switch v-model="form.allow_video" />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="系统" name="system">
          <el-form label-width="120px">
            <el-form-item label="图片广场">
              <el-switch v-model="form.plaza_enabled" />
              <span class="form-suffix">仅展示作者主动发布的公开图片</span>
            </el-form-item>
            <el-form-item label="开放注册">
              <el-switch v-model="form.allow_register" />
            </el-form-item>
            <el-form-item label="注册审核">
              <el-switch v-model="form.register_review" />
              <span class="form-suffix">开启后新用户需审核才能上传</span>
            </el-form-item>
            <el-form-item label="保留用户名">
              <el-input v-model="form.forbidden_username" placeholder="逗号分隔，禁止注册" />
            </el-form-item>
            <el-form-item label="密码登录">
              <el-switch v-model="form.password_login" />
              <span class="form-suffix">关闭后只能通过统一登录进入，同时停用本地注册</span>
            </el-form-item>
            <el-form-item label="外部访问地址">
              <el-input
                v-model="form.external_base_url"
                placeholder="如 https://img.example.com，用于拼接图片外链"
              />
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <HookSlot slot="admin.site_setting" show-title style="margin-top: 16px" />
  </div>
</template>
