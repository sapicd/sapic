<script setup>
import { computed, onMounted, ref } from 'vue'

import { api, errorMessage } from '@/api/client'
import HookSlot from '@/components/hook/HookSlot.vue'
import { t, locale } from '@/i18n'
import { useSiteStore } from '@/stores/site'

const site = useSiteStore()

//: label 宽度按最长标签定，中文「审核拦截时即删除」、英文「Purge on moderation
//: block」都不折行；演示账号区域默认收起，需要配置时再展开。
const labelWidth = computed(() => (locale.value === 'en' ? '220px' : '140px'))
const demoOpen = ref([])

//: 先给 smtp 一个空壳，加载失败时表单绑定也不会炸。
const form = ref({
  smtp: { host: '', port: 25, user: '', password: '', from: '', tls: false },
})
const loading = ref(false)
const editable = ref([])
const tab = ref('site')
const saving = ref(false)
const testMailTo = ref('')
const testingMail = ref(false)

async function loadSettings() {
  loading.value = true
  try {
    const data = await api.get('/settings')
    form.value = data?.items || {}
    editable.value = data?.editable || []
  } catch (error) {
    ElMessage.error(errorMessage(error, t('adminSite.loadFailed')))
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
    ElMessage.success(t('adminSite.saved'))
  } catch (error) {
    ElMessage.error(errorMessage(error, t('adminSite.saveFailed')))
  } finally {
    saving.value = false
  }
}

//: 测试邮件走服务端已保存的配置，改完要先生效再测。
async function sendTestMail() {
  testingMail.value = true
  try {
    const data = await api.post('/settings/smtp/test', {
      json: { to: testMailTo.value.trim() || undefined },
    })
    ElMessage.success(t('adminSite.testSent', { to: data?.to || '' }))
  } catch (error) {
    ElMessage.error(
      t('adminSite.testFailed', { message: errorMessage(error, t('common.unknown')) }),
    )
  } finally {
    testingMail.value = false
  }
}

onMounted(loadSettings)
</script>

<template>
  <div v-loading="loading" class="page">
    <div class="page__header">
      <h2 class="page__title">{{ t('adminSite.title') }}</h2>
      <el-button @click="loadSettings">{{ t('common.refresh') }}</el-button>
    </div>

    <el-card>
      <template #header>
        <div class="card-header">
          <span>{{ t('adminSite.title') }}</span>
          <el-button type="primary" size="small" :loading="saving" @click="saveSettings">
            {{ t('common.save') }}
          </el-button>
        </div>
      </template>

      <el-tabs v-model="tab">
        <el-tab-pane :label="t('adminSite.tabSite')" name="site">
          <el-form :label-width="labelWidth">
            <el-form-item :label="t('adminSite.siteName')">
              <el-input v-model="form.site_name" maxlength="64" />
            </el-form-item>
            <el-form-item :label="t('adminSite.siteKeywords')">
              <el-input
                v-model="form.site_keywords"
                :placeholder="t('adminSite.siteKeywordsPlaceholder')"
              />
            </el-form-item>
            <el-form-item :label="t('adminSite.siteDescription')">
              <el-input v-model="form.site_description" type="textarea" :rows="2" />
            </el-form-item>
            <el-form-item :label="t('adminSite.loginNotice')">
              <el-input
                v-model="form.login_notice"
                :placeholder="t('adminSite.loginNoticePlaceholder')"
                maxlength="64"
              />
            </el-form-item>
            <el-form-item :label="t('adminSite.logoUrl')">
              <el-input v-model="form.site_logo" :placeholder="t('adminSite.logoPlaceholder')" />
            </el-form-item>
            <el-form-item :label="t('adminSite.background')">
              <el-input
                v-model="form.site_background"
                :placeholder="t('adminSite.backgroundPlaceholder')"
              />
            </el-form-item>
            <el-form-item :label="t('adminSite.backgroundMobile')">
              <el-input
                v-model="form.site_background_mobile"
                :placeholder="t('adminSite.backgroundMobilePlaceholder')"
              />
            </el-form-item>
            <el-form-item :label="t('adminSite.backgroundOpacity')">
              <el-slider
                v-model="form.site_background_opacity"
                :min="0"
                :max="1"
                :step="0.1"
                show-input
              />
            </el-form-item>
            <el-form-item :label="t('adminSite.icp')">
              <el-input v-model="form.site_icp" :placeholder="t('adminSite.icpPlaceholder')" />
            </el-form-item>
            <el-form-item :label="t('adminSite.footer')">
              <el-input v-model="form.site_footer" placeholder="SaintIC. All rights reserved." />
            </el-form-item>
            <el-form-item :label="t('adminSite.announcement')">
              <el-input
                v-model="form.site_announcement"
                type="textarea"
                :rows="3"
                :placeholder="t('adminSite.announcementPlaceholder')"
              />
              <span class="form-suffix">{{ t('adminSite.announcementHint') }}</span>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane :label="t('adminSite.tabUpload')" name="upload">
          <el-form :label-width="labelWidth">
            <el-form-item :label="t('adminSite.uploadEnabled')">
              <el-switch v-model="form.upload_enabled" />
              <span class="form-suffix">{{ t('adminSite.uploadEnabledHint') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSite.anonymousUpload')">
              <el-switch v-model="form.allow_anonymous_upload" />
            </el-form-item>
            <el-form-item :label="t('adminSite.uploadNotice')">
              <el-input
                v-model="form.upload_notice"
                type="textarea"
                :rows="2"
                :placeholder="t('adminSite.uploadNoticePlaceholder')"
              />
            </el-form-item>
            <el-form-item :label="t('adminSite.allowedExt')">
              <el-input v-model="form.upload_allowed_ext" placeholder="jpg,png,gif,webp,mp4" />
            </el-form-item>
            <el-form-item :label="t('adminSite.imageMaxSize')">
              <el-input-number
                v-model="form.upload_image_max_size"
                :min="1"
                :max="1024"
              />
              <span class="form-suffix">{{ t('adminSite.imageMaxSizeUnit') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSite.videoMaxSize')">
              <el-input-number
                v-model="form.upload_video_max_size"
                :min="1"
                :max="1024"
              />
              <span class="form-suffix">{{ t('adminSite.videoMaxSizeUnit') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSite.uploadCountLimit')">
              <el-input-number v-model="form.upload_count_limit" :min="1" :max="100" />
              <span class="form-suffix">{{ t('adminSite.uploadCountLimitUnit') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSite.allowVideo')">
              <el-switch v-model="form.allow_video" />
            </el-form-item>
            <el-form-item :label="t('adminSite.expireDefault')">
              <el-input-number
                v-model="form.image_expire_default_days"
                :min="0"
                :max="3650"
              />
              <span class="form-suffix">{{ t('adminSite.expireDefaultUnit') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSite.expireMax')">
              <el-input-number v-model="form.image_expire_max_days" :min="0" :max="3650" />
              <span class="form-suffix">{{ t('adminSite.expireMaxUnit') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSite.replica')">
              <el-switch v-model="form.storage_replica" />
              <span class="form-suffix">{{ t('adminSite.replicaHint') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSite.linkMode')">
              <el-select v-model="form.link_mode" style="width: 220px">
                <el-option value="raw" :label="t('adminSite.linkModeRaw')" />
                <el-option value="direct" :label="t('adminSite.linkModeDirect')" />
              </el-select>
              <span class="form-suffix">{{ t('adminSite.linkModeHint') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSite.rawRateLimit')">
              <el-input-number v-model="form.raw_rate_limit" :min="0" :max="60000" />
              <span class="form-suffix">{{ t('adminSite.rawRateLimitHint') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSite.hotlinkAllowEmpty')">
              <el-switch v-model="form.hotlink_allow_empty" />
              <span class="form-suffix">{{ t('adminSite.hotlinkAllowEmptyHint') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSite.fetchProxy')">
              <el-input
                v-model="form.upload_fetch_proxy"
                :placeholder="t('adminSite.fetchProxyPlaceholder')"
              />
              <span class="form-suffix">{{ t('adminSite.fetchProxyHint') }}</span>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane :label="t('adminSite.tabSystem')" name="system">
          <el-form :label-width="labelWidth">
            <el-form-item :label="t('adminSite.apiRateLimit')">
              <el-input-number v-model="form.api_rate_limit" :min="0" :max="6000" />
              <span class="form-suffix">{{ t('adminSite.apiRateLimitHint') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSite.rawIpMode')">
              <el-select v-model="form.raw_ip_mode" style="width: 220px">
                <el-option value="off" :label="t('adminSite.rawIpModeOff')" />
                <el-option value="allow" :label="t('adminSite.rawIpModeAllow')" />
                <el-option value="deny" :label="t('adminSite.rawIpModeDeny')" />
              </el-select>
              <span class="form-suffix">{{ t('adminSite.rawIpModeHint') }}</span>
            </el-form-item>
            <el-form-item
              v-if="form.raw_ip_mode && form.raw_ip_mode !== 'off'"
              :label="t('adminSite.rawIpList')"
            >
              <el-input
                v-model="form.raw_ip_list"
                type="textarea"
                :rows="3"
                :placeholder="t('adminSite.rawIpListPlaceholder')"
              />
              <span class="form-suffix">{{ t('adminSite.rawIpListHint') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSite.plaza')">
              <el-switch v-model="form.plaza_enabled" />
              <span class="form-suffix">{{ t('adminSite.plazaHint') }}</span>
            </el-form-item>
            <!--: 「用户自定义存储」(allow_user_backends) 暂不暴露：用户端的管理界面还没做，
                 开关打开后普通用户看不到任何入口，等界面就绪再放回来。 -->
            <el-form-item :label="t('adminSite.allowRegister')">
              <el-switch v-model="form.allow_register" />
            </el-form-item>
            <el-form-item :label="t('adminSite.registerReview')">
              <el-switch v-model="form.register_review" />
              <span class="form-suffix">{{ t('adminSite.registerReviewHint') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSite.reviewAutoPurge')">
              <el-switch v-model="form.review_auto_purge" />
              <span class="form-suffix">{{ t('adminSite.reviewAutoPurgeHint') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSite.forbiddenUsername')">
              <el-input
                v-model="form.forbidden_username"
                :placeholder="t('adminSite.forbiddenUsernamePlaceholder')"
              />
            </el-form-item>
            <el-form-item :label="t('adminSite.passwordLogin')">
              <el-switch v-model="form.password_login" />
              <span class="form-suffix">{{ t('adminSite.passwordLoginHint') }}</span>
            </el-form-item>
            <!--: 演示账号是低频配置，手风琴默认收起，不让它把系统页撑长。 -->
            <el-collapse v-model="demoOpen" class="demo-collapse">
              <el-collapse-item :title="t('adminSite.demoTitle')" name="demo">
                <el-form-item :label="t('adminSite.demoEnabled')">
                  <el-switch v-model="form.demo_rotate_enabled" />
                  <span class="form-suffix">{{ t('adminSite.demoEnabledHint') }}</span>
                </el-form-item>
                <el-form-item :label="t('adminSite.demoUsername')">
                  <el-input
                    v-model="form.demo_rotate_username"
                    :placeholder="t('adminSite.demoUsernamePlaceholder')"
                  />
                </el-form-item>
                <el-form-item :label="t('adminSite.demoPassword')">
                  <el-input
                    v-model="form.demo_rotate_password"
                    type="password"
                    show-password
                    :placeholder="t('adminSite.demoPasswordPlaceholder')"
                  />
                </el-form-item>
                <el-form-item :label="t('adminSite.demoInterval')">
                  <el-input-number
                    v-model="form.demo_rotate_interval"
                    :min="60"
                    :max="86400"
                    :step="60"
                  />
                  <span class="form-suffix">{{ t('adminSite.demoIntervalHint') }}</span>
                </el-form-item>
              </el-collapse-item>
            </el-collapse>
          </el-form>
        </el-tab-pane>

        <el-tab-pane :label="t('adminSite.tabMail')" name="mail">
          <el-alert
            type="info"
            :closable="false"
            show-icon
            style="margin-bottom: 16px"
            :title="t('adminSite.mailAlertTitle')"
            :description="t('adminSite.mailAlertDesc')"
          />
          <el-form :label-width="labelWidth">
            <el-form-item :label="t('adminSite.smtpHost')">
              <el-input
                v-model="form.smtp.host"
                :placeholder="t('adminSite.smtpHostPlaceholder')"
              />
            </el-form-item>
            <el-form-item :label="t('adminSite.port')">
              <el-input-number v-model="form.smtp.port" :min="1" :max="65535" />
              <span class="form-suffix">{{ t('adminSite.portHint') }}</span>
            </el-form-item>
            <el-form-item label="STARTTLS">
              <el-switch v-model="form.smtp.tls" />
              <span class="form-suffix">{{ t('adminSite.starttlsHint') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSite.smtpUser')">
              <el-input
                v-model="form.smtp.user"
                :placeholder="t('adminSite.smtpAuthPlaceholder')"
              />
            </el-form-item>
            <el-form-item :label="t('adminSite.smtpPassword')">
              <el-input
                v-model="form.smtp.password"
                type="password"
                show-password
                :placeholder="t('adminSite.smtpAuthPlaceholder')"
              />
              <span class="form-suffix">{{ t('adminSite.smtpPasswordHint') }}</span>
            </el-form-item>
            <el-form-item :label="t('adminSite.smtpFrom')">
              <el-input v-model="form.smtp.from" placeholder="sapic@example.com" />
            </el-form-item>
            <el-form-item :label="t('adminSite.testRecipient')">
              <el-input
                v-model="testMailTo"
                :placeholder="t('adminSite.testRecipientPlaceholder')"
              />
            </el-form-item>
            <el-form-item>
              <el-button :loading="testingMail" @click="sendTestMail">
                {{ t('adminSite.sendTest') }}
              </el-button>
              <span class="form-suffix">{{ t('adminSite.testHint') }}</span>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <HookSlot slot="admin.site_setting" show-title style="margin-top: 16px" />
  </div>
</template>
