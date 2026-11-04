import {
  ArrowDown,
  Connection,
  CopyDocument,
  Delete,
  FolderOpened,
  Grid,
  HomeFilled,
  Key,
  Picture,
  Search,
  Setting,
  Tools,
  UploadFilled,
  User,
  UserFilled,
  View,
} from '@element-plus/icons-vue'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import './styles.css'

//: 菜单与节点图标都用字符串引用，只需要全局注册实际用到的那几个。
const GLOBAL_ICONS = [
  ArrowDown,
  Connection,
  CopyDocument,
  Delete,
  FolderOpened,
  Grid,
  HomeFilled,
  Key,
  Picture,
  Search,
  Setting,
  Tools,
  UploadFilled,
  User,
  UserFilled,
  View,
]

const app = createApp(App)

GLOBAL_ICONS.forEach((icon) => {
  app.component(icon.name, icon)
})

app.use(createPinia())
app.use(router)
app.mount('#app')
