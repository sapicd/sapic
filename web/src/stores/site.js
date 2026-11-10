import { defineStore } from 'pinia'

import { api } from '@/api/client'

export const useSiteStore = defineStore('site', {
  state: () => ({
    name: 'sapic',
    keywords: '',
    description: '',
    logo: '',
    background: '',
    backgroundMobile: '',
    backgroundOpacity: 0.6,
    icp: '',
    footer: 'SaintIC. All rights reserved.',
    announcement: '',
    about: '',
    uploadNotice: '',
    //: 单文件上限（MB）按媒体类型分开。
    uploadImageMaxSize: 10,
    uploadVideoMaxSize: 20,
    uploadCountLimit: 10,
    uploadAllowedExt: '',
    allowVideo: true,
    //: 图片有效期（天）：0 表示默认永久 / 不限制上限。
    imageExpireDefaultDays: 0,
    imageExpireMaxDays: 0,
    allowRegister: true,
    passwordLogin: true,
    //: 未配置 SMTP 时验证邮件发不出去，相关入口直接隐藏。
    mailEnabled: false,
    allowAnonymousUpload: false,
    //: 与后端默认值一致：个人图床形态下广场是关闭的。
    plazaEnabled: false,
    version: '',
    loaded: false,
  }),

  getters: {
    //: 未配置站点 Logo 时用内置的旧版 logo。
    logoUrl: (state) => state.logo || `${import.meta.env.BASE_URL}logo.png`,

    //: 未配置站点背景时用内置的旧版背景图，保证视觉统一。
    backgroundStyle: (state) => ({
      backgroundImage: `url("${state.background || '/background.jpg'}")`,
    }),

    //: accept 属性：站点白名单 + 视频开关。
    uploadAccept: (state) => {
      const videoExts = ['.mp4', '.webm', '.mov', '.m4v', '.avi']
      const exts = (
        state.uploadAllowedExt
          ? state.uploadAllowedExt.split(',')
          : ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'ico', 'svg', ...videoExts]
      )
        .map((item) => `.${item.trim().replace(/^\./, '')}`)
        .filter((item) => item !== '.')
      const allowed = state.allowVideo
        ? exts
        : exts.filter((item) => !videoExts.includes(item))
      return allowed.join(',') || 'image/*'
    },
  },

  actions: {
    async load() {
      try {
        const data = await api.get('/site')
        this.name = data?.name || 'sapic'
        this.keywords = data?.keywords || ''
        this.description = data?.description || ''
        this.logo = data?.logo || ''
        this.background = data?.background || ''
        this.backgroundMobile = data?.background_mobile || ''
        this.backgroundOpacity = Number(data?.background_opacity ?? 0.6)
        this.icp = data?.icp || ''
        this.footer = data?.footer || ''
        this.announcement = data?.announcement || ''
        this.about = data?.about || ''
        this.uploadNotice = data?.upload_notice || ''
        this.uploadImageMaxSize = Number(data?.upload_image_max_size ?? 10)
        this.uploadVideoMaxSize = Number(data?.upload_video_max_size ?? 20)
        this.uploadCountLimit = Number(data?.upload_count_limit ?? 10)
        this.uploadAllowedExt = data?.upload_allowed_ext || ''
        this.allowVideo = data?.allow_video !== false
        this.imageExpireDefaultDays = Number(data?.image_expire_default_days ?? 0)
        this.imageExpireMaxDays = Number(data?.image_expire_max_days ?? 0)
        this.allowRegister = data?.allow_register !== false
        this.passwordLogin = data?.password_login !== false
        this.mailEnabled = Boolean(data?.mail_enabled)
        this.allowAnonymousUpload = Boolean(data?.allow_anonymous_upload)
        this.plazaEnabled = data?.plaza_enabled !== false
        this.version = data?.version || ''
      } catch (error) {
        //: 站点信息只影响展示，加载失败时保留默认值。
      } finally {
        this.loaded = true
      }
    },
  },
})
