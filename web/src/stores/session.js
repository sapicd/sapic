import { defineStore } from 'pinia'

import { api, setCsrfToken } from '@/api/client'

export const useSessionStore = defineStore('session', {
  state: () => ({
    user: null,
    csrf: '',
    //: 个人偏好（油猴开关、背景图等），与后端 /auth/settings 一一对应。
    settings: {},
    loaded: false,
  }),

  getters: {
    authenticated: (state) => Boolean(state.user),
    isAdmin: (state) => Boolean(state.user?.is_admin),
    displayName: (state) => state.user?.nickname || state.user?.username || '',
  },

  actions: {
    apply(payload) {
      this.user = payload?.user || null
      this.csrf = payload?.csrf || this.csrf
      setCsrfToken(this.csrf)
    },

    updateUser(user) {
      if (user) this.user = user
    },

    reset() {
      this.user = null
      this.csrf = ''
      this.settings = {}
      this.loaded = true
      setCsrfToken('')
    },

    async loadSettings() {
      if (!this.user) return {}
      const data = await api.get('/auth/settings')
      this.settings = data?.settings || {}
      return this.settings
    },

    async saveSettings(payload) {
      const data = await api.put('/auth/settings', { json: payload })
      this.settings = data?.settings || {}
      return this.settings
    },

    async load() {
      try {
        const data = await api.get('/auth/session')
        this.user = data?.user || null
        this.csrf = data?.csrf || ''
        setCsrfToken(this.csrf)
      } catch (error) {
        this.reset()
      } finally {
        this.loaded = true
      }
      //: 偏好加载失败不能影响登录态，背景退回站点默认即可。
      if (this.user) {
        try {
          await this.loadSettings()
        } catch (error) {
          this.settings = {}
        }
      }
    },

    async login(credentials) {
      const data = await api.post('/auth/login', { json: credentials })
      this.apply(data)
      this.loaded = true
      try {
        await this.loadSettings()
      } catch (error) {
        this.settings = {}
      }
      return data
    },

    async register(payload) {
      return api.post('/auth/register', { json: payload })
    },

    async logout() {
      try {
        await api.post('/auth/logout')
      } finally {
        this.reset()
      }
    },

    async changePassword(payload) {
      const data = await api.put('/auth/password', { json: payload })
      this.csrf = data?.csrf || this.csrf
      setCsrfToken(this.csrf)
      return data
    },

    //: 注销后后端已清会话，这里只负责把前端状态一并归零。
    async deleteAccount(password) {
      await api.del('/auth/account', { json: { password } })
      this.reset()
    },
  },
})
