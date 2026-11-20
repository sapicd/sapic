//: 界面文案的最小实现：没有引入 vue-i18n，词表按区域分组放在 zh.js / en.js，
//: 中文是源语言（缺英文时回落中文），这样新增文案不会因为漏翻而白屏。
//: ``t()`` 内部读 ``locale.value``，在模板里调用即可建立依赖，切换语言会自动重渲染。

import { ref } from 'vue'

import en from './en'
import zh from './zh'

export const LOCALES = [
  { code: 'zh', label: '简体中文', short: '中', element: 'zh-cn' },
  { code: 'en', label: 'English', short: 'EN', element: 'en' },
]

const CATALOGS = { zh, en }
const STORAGE_KEY = 'sapic_locale'

function detect() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && CATALOGS[saved]) return saved
  } catch (error) {
    //: 隐私模式下 localStorage 可能直接抛错，忽略即可。
  }
  const language = String(navigator.language || '').toLowerCase()
  return language.startsWith('zh') ? 'zh' : 'en'
}

export const locale = ref(detect())

export function currentLocale() {
  return locale.value
}

export function setLocale(code) {
  if (!CATALOGS[code]) return
  locale.value = code
  try {
    localStorage.setItem(STORAGE_KEY, code)
  } catch (error) {
    //: 存不进去只影响下次打开，不影响本次切换。
  }
  document.documentElement.lang = code === 'zh' ? 'zh-CN' : 'en'
}

//: 首次进入时把 <html lang> 与默认语言对齐，避免屏幕阅读器读错语言。
document.documentElement.lang = locale.value === 'zh' ? 'zh-CN' : 'en'

function lookup(catalog, key) {
  return String(key)
    .split('.')
    .reduce((node, part) => (node && typeof node === 'object' ? node[part] : undefined), catalog)
}

/**
 * Translate ``key`` into the active locale.
 *
 * ``params`` fills ``{name}`` placeholders, e.g. ``t('common.count', { n: 3 })``.
 * A missing key falls back to Chinese, then to the key itself (visible in the
 * UI, never a runtime error).
 */
export function t(key, params) {
  const value = lookup(CATALOGS[locale.value], key) ?? lookup(CATALOGS.zh, key)
  if (typeof value !== 'string') return String(key ?? '')
  if (!params) return value
  return value.replace(/\{(\w+)\}/g, (match, name) =>
    params[name] === undefined || params[name] === null ? match : String(params[name]),
  )
}

/** Whether ``key`` is known to the source catalogue (Chinese). */
export function hasKey(key) {
  return typeof lookup(CATALOGS.zh, key) === 'string'
}

export function useI18n() {
  return { t, locale, setLocale }
}

export default { install(app) {
  //: 模板里可以直接写 ``{{ t('nav.home') }}``，不用每个组件都 import。
  app.config.globalProperties.t = t
  app.config.globalProperties.$t = t
} }
