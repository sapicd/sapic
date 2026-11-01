import { defineStore } from 'pinia'

import { api, setCsrfToken } from '@/api/client'

export const useSessionStore = defineStore('session', {
  state: () => ({
    user: null,
    csrf: '',
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
      this.loaded = true
      setCsrfToken('')
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
    },

    async login(credentials) {
      const data = await api.post('/auth/login', { json: credentials })
      this.apply(data)
      this.loaded = true
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
  },
})
