import { existsSync, readdirSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import Components from 'unplugin-vue-components/vite'
import { defineConfig } from 'vite'

const ELEMENT_COMPONENTS_DIR = fileURLToPath(
  new URL('./node_modules/element-plus/es/components', import.meta.url),
)

//: Element Plus 的组件样式是按需引入的（`<组件>/style/css`），Vite 只有在首次访问用到某个
//: 组件的页面时才会发现它们，每发现一批就重新预构建并整页 reload（开发期「点开新页面就刷新」）。
//: 这里把现有组件样式全部列进预构建，把多次刷新收敛到启动阶段；生产构建的产物不受影响。
//: 组件清单从磁盘读，Element Plus 升级新增组件时不用改配置。
function elementStyleDeps() {
  if (!existsSync(ELEMENT_COMPONENTS_DIR)) return []
  return readdirSync(ELEMENT_COMPONENTS_DIR)
    .filter((name) => existsSync(`${ELEMENT_COMPONENTS_DIR}/${name}/style/css.mjs`))
    .map((name) => `element-plus/es/components/${name}/style/css`)
}

//: 开发期把 API 与图片请求代理到 Flask，保持同源，Cookie 会话才能生效。
export default defineConfig({
  plugins: [
    vue(),
    //: Element Plus 按需引入：组件由模板自动注册，ElMessage 等 API 自动导入，样式随之注入。
    AutoImport({ resolvers: [ElementPlusResolver()], dts: false }),
    Components({ resolvers: [ElementPlusResolver()], dts: false }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  optimizeDeps: {
    include: [
      //: 自动导入的组件都从包入口具名引入（构建时再 tree-shake），所以入口也要预构建，
      //: 否则第一个用到组件的页面同样会触发一次重新优化。
      'element-plus/es',
      'element-plus/es/locale/lang/zh-cn',
      ...elementStyleDeps(),
      '@element-plus/icons-vue',
      'pinia',
      'vue',
      'vue-router',
    ],
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:9514',
        changeOrigin: false,
      },
      //: 图片直链前缀，用正则锚定，避免误伤其它以 /raw 开头的路径。
      '^/raw/': {
        target: 'http://127.0.0.1:9514',
        changeOrigin: false,
      },
      //: 油猴脚本在 /api/v2 下，已被上面的 /api 代理覆盖，无需单列。
    },
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      output: {
        //: element-plus 按需引入后没有单一入口，交给 Rollup 自行拆包（强行归并会把未用组件带上），
        //: 只把变化频率最低的 vue 家族单独提取。
        manualChunks(id) {
          if (/[\\/]node_modules[\\/](vue|vue-router|pinia|@vue)[\\/]/.test(id)) {
            return 'vue'
          }
        },
      },
    },
  },
})
