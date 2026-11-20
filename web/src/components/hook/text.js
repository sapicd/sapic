//: 钩子节点的文案统一走这里：节点可带 ``text_key`` / ``label_key`` 等 i18n 键，
//: 词表有译文就用译文，没有就回落到钩子给的原文（第三方钩子可以只写一种语言）。
import { hasKey, t } from '@/i18n'

export function nodeText(node, field = 'text') {
  const key = node[`${field}_key`]
  const value = key && hasKey(key) ? t(key) : node[field]
  return value === undefined || value === null ? '' : value
}

//: 钩子 manifest 文案：先看钩子自己声明的键，再按模块名兜底（``hooks.<module>.title``），
//: 都没有才显示钩子原文——第三方钩子只写一种语言时，站点仍可在词表里补译文。
export function hookText(name, field, fallback = '', declaredKey = '') {
  if (declaredKey && hasKey(declaredKey)) return t(declaredKey)
  if (name) {
    const key = `hooks.${name}.${field}`
    if (hasKey(key)) return t(key)
  }
  return fallback || ''
}
