import { createRouter, createWebHistory } from 'vue-router'

import { useSessionStore } from '@/stores/session'
import { useSiteStore } from '@/stores/site'

const routes = [
  {
    path: '/',
    name: 'upload',
    component: () => import('@/views/UploadView.vue'),
    meta: { title: '首页' },
  },
  { path: '/upload', redirect: { name: 'upload' } },
  {
    path: '/plaza',
    name: 'plaza',
    component: () => import('@/views/PlazaView.vue'),
    meta: { title: '广场' },
  },
  {
    path: '/images',
    name: 'images',
    component: () => import('@/views/ImagesView.vue'),
    //: 图片列表是个人图库，未登录没有内容可看。
    meta: { requiresAuth: true, title: '图片' },
  },
  {
    path: '/images/:sha',
    name: 'image-detail',
    component: () => import('@/views/ImageDetailView.vue'),
    meta: { title: '图片详情' },
  },
  {
    path: '/albums',
    name: 'albums',
    component: () => import('@/views/AlbumsView.vue'),
    meta: { requiresAuth: true, title: '相册' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { requiresAuth: true, title: '账号设置' },
  },
  {
    path: '/admin',
    name: 'admin',
    component: () => import('@/views/AdminView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true, title: '站点设置' },
  },
  {
    path: '/admin/hooks',
    name: 'admin-hooks',
    component: () => import('@/views/HooksView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true, title: '钩子管理' },
  },
  {
    path: '/admin/users',
    name: 'admin-users',
    component: () => import('@/views/UsersView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true, title: '用户管理' },
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { guestOnly: true, title: '登录' },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { guestOnly: true, title: '注册' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const session = useSessionStore()
  const site = useSiteStore()
  if (!site.loaded) {
    await site.load()
  }
  if (!session.loaded) {
    await session.load()
  }
  if (to.meta.requiresAuth && !session.authenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.requiresAdmin && !session.isAdmin) {
    return { name: 'upload' }
  }
  if (to.meta.guestOnly && session.authenticated) {
    return { name: 'upload' }
  }
  return true
})

router.afterEach((to) => {
  const site = useSiteStore()
  document.title = to.meta.title ? `${to.meta.title} · ${site.name}` : site.name
})

export default router
