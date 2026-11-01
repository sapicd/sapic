import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import Components from 'unplugin-vue-components/vite'
import { defineConfig } from 'vite'

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
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:9514',
        changeOrigin: false,
      },
      //: 必须是正则，否则 /i 前缀会连 /images 一起代理到后端。
      '^/i/': {
        target: 'http://127.0.0.1:9514',
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      output: {
        //: element-plus 按需引入后没有单一入口，交给 Rollup 自行拆包（强行归并会把未用组件带上），
        //: 只把变化频率最低的 vue 家族单独提取。
        manualChunks(id) {
          if (/[\\/]node_modules[\\/](vue|vue-router|pinia|@vue)[\\/]/.test(id)) return 'vue'
        },
      },
    },
  },
})
