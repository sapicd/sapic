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
    //: 后台是一个壳：侧栏在四个页面间切换，URL 各自独立。
    //: ``/admin`` 直接渲染站点设置（不做重定向），未授权访问由守卫改写成 404，
    //: 这样地址栏不会有任何跳转痕迹；``/admin/setting`` 保留为规范地址。
    path: '/admin',
    component: () => import('@/layout/AdminLayout.vue'),
    meta: { requiresAdmin: true },
    children: [
      {
        path: '',
        component: () => import('@/views/AdminView.vue'),
        meta: { title: '站点设置' },
      },
      {
        path: 'setting',
        name: 'admin',
        component: () => import('@/views/AdminView.vue'),
        meta: { title: '站点设置' },
      },
      {
        path: 'hooks',
        name: 'admin-hooks',
        component: () => import('@/views/HooksView.vue'),
        meta: { title: '钩子管理' },
      },
      {
        path: 'backends',
        name: 'admin-backends',
        component: () => import('@/views/BackendsView.vue'),
        meta: { title: '存储后端' },
      },
      {
        path: 'users',
        name: 'admin-users',
        component: () => import('@/views/UsersView.vue'),
        meta: { title: '用户管理' },
      },
    ],
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
    meta: { title: '页面不存在' },
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
  //: 广场被后台关掉后，直接访问 /plaza 也退回首页。
  if (to.name === 'plaza' && !site.plazaEnabled) {
    return { name: 'upload' }
  }
  //: 后台对「未登录」与「非管理员」一律当作不存在：不跳登录页、也不提示无权限，
  //: 保持 URL 不变直接把内容渲染成 404，避免向未授权访问者暴露后台入口。
  //: 真正的权限由后端 admin_required 把关，这里只是不给出入口与提示。
  if (to.meta.requiresAdmin && !(session.authenticated && session.isAdmin)) {
    return {
      name: 'not-found',
      params: { pathMatch: to.path.split('/').filter(Boolean) },
      query: to.query,
      hash: to.hash,
      replace: true,
    }
  }
  if (to.meta.requiresAuth && !session.authenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
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
