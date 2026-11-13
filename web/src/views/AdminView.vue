<script setup>
import { onMounted, ref } from 'vue'

import { api, errorMessage } from '@/api/client'
import HookSlot from '@/components/hook/HookSlot.vue'
import { useSiteStore } from '@/stores/site'

const site = useSiteStore()

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

//: 测试邮件走服务端已保存的配置，改完要先生效再测。
async function sendTestMail() {
  testingMail.value = true
  try {
    const data = await api.post('/settings/smtp/test', {
      json: { to: testMailTo.value.trim() || undefined },
    })
    ElMessage.success(`测试邮件已发送至 ${data?.to || ''}`)
  } catch (error) {
    ElMessage.error(`发送失败：${errorMessage(error, '未知错误')}`)
  } finally {
    testingMail.value = false
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
            <el-form-item label="登录页提示">
              <el-input
                v-model="form.login_notice"
                placeholder="显示在登录卡片标题下方，留空则不显示"
                maxlength="64"
              />
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
              <el-input
                v-model="form.site_announcement"
                type="textarea"
                :rows="3"
                placeholder="支持 **加粗**、[文字](https://链接)，空行分段"
              />
              <span class="form-suffix">
                只解析加粗与链接，其余内容按纯文本显示（不执行任何 HTML 标签）
              </span>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="上传" name="upload">
          <el-form label-width="140px">
            <el-form-item label="允许上传">
              <el-switch v-model="form.upload_enabled" />
              <span class="form-suffix">
                关闭后只冻结新增上传（含匿名/令牌/油猴/网址抓取），已有图片照常访问与管理
              </span>
            </el-form-item>
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
            <el-form-item label="图片大小限制">
              <el-input-number
                v-model="form.upload_image_max_size"
                :min="1"
                :max="1024"
              />
              <span class="form-suffix">MB / 张</span>
            </el-form-item>
            <el-form-item label="视频大小限制">
              <el-input-number
                v-model="form.upload_video_max_size"
                :min="1"
                :max="1024"
              />
              <span class="form-suffix">
                MB / 个；不要把进程级 sapic_maxupload 设得比它小
              </span>
            </el-form-item>
            <el-form-item label="首页上传数量限制">
              <el-input-number v-model="form.upload_count_limit" :min="1" :max="100" />
              <span class="form-suffix">个 / 次</span>
            </el-form-item>
            <el-form-item label="允许视频">
              <el-switch v-model="form.allow_video" />
            </el-form-item>
            <el-form-item label="默认有效期">
              <el-input-number
                v-model="form.image_expire_default_days"
                :min="0"
                :max="3650"
              />
              <span class="form-suffix">天，0 表示永久保留</span>
            </el-form-item>
            <el-form-item label="有效期上限">
              <el-input-number v-model="form.image_expire_max_days" :min="0" :max="3650" />
              <span class="form-suffix">
                天，0 表示不限制；设置后不再允许永久图片，未指定时按上限
              </span>
            </el-form-item>
            <el-form-item label="多副本上传">
              <el-switch v-model="form.storage_replica" />
              <span class="form-suffix">
                priority 数值最小的后端同步写入，其余启用的后端在后台异步补副本（失败不影响上传）
              </span>
            </el-form-item>
            <el-form-item label="下载代理">
              <el-input
                v-model="form.upload_fetch_proxy"
                placeholder="http://127.0.0.1:7890，留空表示直连"
              />
              <span class="form-suffix">
                网址上传由服务端抓取，直连失败（超时 / 连接错误 / 解析不了）后才走该代理兜底，
                能直连的源不绕路；支持 http(s) 代理与 http://user:pass@host:port
              </span>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="系统" name="system">
          <el-form label-width="120px">
            <el-form-item label="图片广场">
              <el-switch v-model="form.plaza_enabled" />
              <span class="form-suffix">仅展示作者主动发布的公开图片</span>
            </el-form-item>
            <!--: 「用户自定义存储」(allow_user_backends) 暂不暴露：用户端的管理界面还没做，
                 开关打开后普通用户看不到任何入口，等界面就绪再放回来。 -->
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

        <el-tab-pane label="邮件" name="mail">
          <el-form label-width="120px">
            <el-form-item label="SMTP 服务器">
              <el-input
                v-model="form.smtp.host"
                placeholder="smtp.example.com，留空表示停用邮件"
              />
            </el-form-item>
            <el-form-item label="端口">
              <el-input-number v-model="form.smtp.port" :min="1" :max="65535" />
              <span class="form-suffix">25 / 465（SSL）/ 587（STARTTLS）</span>
            </el-form-item>
            <el-form-item label="STARTTLS">
              <el-switch v-model="form.smtp.tls" />
              <span class="form-suffix">465 端口走 SSL，这里不勾选</span>
            </el-form-item>
            <el-form-item label="用户名">
              <el-input v-model="form.smtp.user" placeholder="可留空，表示无需认证" />
            </el-form-item>
            <el-form-item label="密码 / 授权码">
              <el-input
                v-model="form.smtp.password"
                type="password"
                show-password
                placeholder="可留空，表示无需认证"
              />
              <span class="form-suffix">已保存的密钥不会回显，保持 ******** 即不修改</span>
            </el-form-item>
            <el-form-item label="发件人">
              <el-input v-model="form.smtp.from" placeholder="sapic@example.com" />
            </el-form-item>
            <el-form-item label="测试收件人">
              <el-input v-model="testMailTo" placeholder="留空发给当前管理员邮箱" />
            </el-form-item>
            <el-form-item>
              <el-button :loading="testingMail" @click="sendTestMail">
                发送测试邮件
              </el-button>
              <span class="form-suffix">先保存再用已保存的配置测试</span>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <HookSlot slot="admin.site_setting" show-title style="margin-top: 16px" />
  </div>
</template>
