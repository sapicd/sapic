# sapic web (v2)

sapic 的前端：Vue 3 + Vite + Element Plus 单页应用。与后端 `server/` **同源**交互——
数据走 `/api/v2/*`（统一信封 `{code, message, data}`），图片走 `/raw/<sha>`；
生产环境由 nginx 托管构建产物并把这两个前缀反代给 Flask（容器镜像已内置，见 `DEPLOY.md`）。

## 环境要求

- Node.js 23+、pnpm 8（`packageManager: pnpm@8.14.1`，`corepack enable` 即可用）
- 后端跑在 `127.0.0.1:9514`（仓库根 `make dev`）

## 开发

```bash
pnpm install      # 仓库根 make setup 会一并安装
pnpm run dev      # http://127.0.0.1:5173
pnpm run build    # 构建到 dist/
pnpm run preview  # 预览构建产物
```

`vite.config.js` 把 `/api` 与 `/raw/` 代理到 `127.0.0.1:9514`，保持同源，Cookie 会话与 CSRF
才能生效。前后端不同域部署时用 `VITE_API_BASE` 指定 API 前缀（默认 `/api/v2`）。

## 目录

| 路径 | 内容 |
| --- | --- |
| `src/api/client.js` | 唯一的请求封装：信封解析、CSRF 头、401 回调、错误归一（`errorMessage`） |
| `src/api/messages.js` | 后端英文 `message` → 中文的词典与模板规则（`localizeMessage`） |
| `src/stores/session.js` | 当前用户、CSRF、`authenticated` / `isAdmin` |
| `src/stores/site.js` | 站点信息（名称、背景、注册/匿名上传/广场开关），来自 `GET /api/v2/site` |
| `src/router/index.js` | 路由与守卫（未登录跳登录、后台未授权渲染 404、广场关闭回首页） |
| `src/layout/AppLayout.vue` | 顶部导航 / 全屏背景 / 页脚外壳 |
| `src/layout/AdminLayout.vue` | 后台侧栏壳：站点设置 / 钩子 / 存储后端 / 用户 |
| `src/components/hook/` | 插件节点渲染：`HookSlot` 按插槽名拉节点树，`NodeRenderer` 递归分发词表 |
| `src/components/AvatarCropper.vue` | 头像裁剪 |
| `src/views/` | 页面组件，与下表的页面一一对应 |
| `src/utils/format.js` | 时间（后端是 10 位秒级时间戳）、体积等展示格式化 |
| `public/` | 静态资源：`logo.png` / `favicon.png` / 默认背景 `background.jpg` |

## 页面

| 路由 | 组件 | 说明 |
| --- | --- | --- |
| `/` | `UploadView` | 上传：拖拽 / 粘贴 / 远程 URL / 队列（`/upload` 重定向到首页） |
| `/images`、`/images/:sha` | `ImagesView`、`ImageDetailView` | 个人图库与图片详情 |
| `/albums` | `AlbumsView` | 相册管理与共享 |
| `/plaza` | `PlazaView` | 图片广场，站点关闭 `plaza_enabled` 时回首页 |
| `/settings` | `SettingsView` | 账号设置：资料、邮箱、令牌、统一登录、个性化 |
| `/login`、`/register` | `LoginView`、`RegisterView` | 已登录访问会跳回首页 |
| `/admin`、`/admin/setting`、`/admin/hooks`、`/admin/backends`、`/admin/users` | `AdminView` 等四个 | 后台壳（`AdminLayout`）；未登录或非管理员一律渲染 404 |
| 其它 | `NotFoundView` | 404 |

`requiresAuth` / `requiresAdmin` / `guestOnly` 写在路由 `meta` 里，判定集中在 `router.beforeEach`。

## 约定

完整规则见仓库根 `AGENTS.md` 的「前端规范（Vue 3 / Element Plus）」，要点：

- `<script setup>`；组件 PascalCase、函数 camelCase，变量只用 `let` / `const`
- 接口一律走 `api/client.js`，不要散落 `fetch`；错误提示用 `errorMessage(error, fallback)`，
  不要直接 `ElMessage.error(error.message)`（后端 message 是英文，需经 `messages.js` 本地化）
- 界面**固定中文**，不引入 `vue-i18n`；Element Plus 文案由 `App.vue` 的
  `<el-config-provider :locale="zhCn">` 统一提供
- Element Plus 按需引入：模板直接写 `<el-xxx>`、脚本直接用 `ElMessage`，
  **不要**再显式 `import ... from 'element-plus'`
- 插件界面不写业务分支：`HookSlot` / `NodeRenderer` 只认后端声明的词表，未知类型静默跳过；
  按钮只调用后端已校验的 `action`
- 模板里用字符串图标名（`icon: 'Brush'` + `<component :is="icon" />`）时，必须在
  `src/main.js` 的 `GLOBAL_ICONS` 注册，否则图标静默不渲染
- 视频按 `images.is_video` 渲染原生 `<video>`（列表里用 `muted preload="metadata"` 取首帧当封面），
  不要用 `el-image` 渲染视频

## 构建与部署

`pnpm run build` 产出 `dist/`，交给静态服务器托管并反代 `/api`、`/raw/` 到后端；
容器镜像在构建阶段已完成这一步，**不需要单独部署前端**（见 `DEPLOY.md` 第 3.7 节）。
