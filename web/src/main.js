import {
  ArrowDown,
  Brush,
  Connection,
  CopyDocument,
  Delete,
  FolderOpened,
  Grid,
  HomeFilled,
  Key,
  Link,
  Menu,
  Picture,
  Search,
  Setting,
  Switch,
  Tools,
  UploadFilled,
  User,
  UserFilled,
  View,
} from '@element-plus/icons-vue'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import i18n from './i18n'
import router from './router'
import './styles.css'

//: 菜单与节点图标都用字符串引用，只需要全局注册实际用到的那几个。
const GLOBAL_ICONS = [
  ArrowDown,
  Brush,
  Connection,
  CopyDocument,
  Delete,
  FolderOpened,
  Grid,
  HomeFilled,
  Key,
  Link,
  Menu,
  Picture,
  Search,
  Setting,
  Switch,
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
//: 必须在 router 之前注册：路由守卫与视图渲染都可能马上用到 ``t()``。
app.use(i18n)
app.use(router)
app.mount('#app')
