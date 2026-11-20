//: 钩子节点的文案统一走这里：节点可带 ``text_key`` / ``label_key`` 等 i18n 键，
//: 词表有译文就用译文，没有就回落到钩子给的原文（第三方钩子可以只写一种语言）。
import { hasKey, t } from '@/i18n'

function translated(key) {
  return key && hasKey(key) ? t(key) : ''
}

/**
 * Translate the ``field`` text of a hook node.
 *
 * Order: the key the node declares (``label_key`` …), then the module-scoped
 * fallback ``hooks.<hook>.fields.<key>.<field>`` for third-party hooks that
 * never declare keys, and finally the hook's own literal text.
 */
export function nodeText(node, field = 'text', hook = '') {
  const declared = translated(node[`${field}_key`])
  if (declared) return declared
  if (hook && node.key) {
    const scoped = translated(`hooks.${hook}.fields.${node.key}.${field}`)
    if (scoped) return scoped
  }
  const value = node[field]
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
