import {
  Connection,
  CopyDocument,
  Delete,
  Download,
  Link,
  Refresh,
  Setting,
  Star,
  Tools,
  Upload,
} from '@element-plus/icons-vue'

//: 钩子只能使用 builtin/brand 前缀的名义图标，前端负责映射到自己的图标库。
const ICONS = {
  'builtin:plug': Connection,
  'builtin:external': Link,
  'builtin:link': Link,
  'builtin:refresh': Refresh,
  'builtin:settings': Setting,
  'builtin:upload': Upload,
  'builtin:download': Download,
  'builtin:copy': CopyDocument,
  'builtin:tool': Tools,
  'builtin:star': Star,
  'builtin:delete': Delete,
}

export function iconOf(name) {
  if (!name) return undefined
  const key = String(name)
  if (ICONS[key]) return ICONS[key]
  if (key.startsWith('brand:')) return Link
  return ICONS[`builtin:${key.split(':').pop()}`]
}
