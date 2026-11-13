//: 公告只支持最少的排版语法：**加粗**、[文字](https://链接)、单换行换行、空行分段。
//: 这里只把文本解析成节点数据，由组件构造成真实节点，全程不用 v-html，
//: 所以公告里的任何标签都只会被当成文字显示（没有 XSS 面）。

const INLINE_RE = /\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)\s]+)\)/g

//: 链接只认这三种协议，`javascript:` / `data:` 之类一律按纯文本显示。
const SAFE_SCHEMES = ['http://', 'https://', 'mailto:']

export function parseRichText(text) {
  const source = String(text || '').replace(/\r\n?/g, '\n')
  const blocks = []
  for (const raw of source.split(/\n{2,}/)) {
    const lines = raw.split('\n').filter((line) => line.trim() !== '')
    if (!lines.length) continue
    const children = []
    lines.forEach((line, index) => {
      if (index) children.push({ type: 'br' })
      children.push(...parseInline(line))
    })
    blocks.push({ type: 'paragraph', children })
  }
  return blocks
}

function safeHref(url) {
  const lower = url.toLowerCase()
  return SAFE_SCHEMES.some((scheme) => lower.startsWith(scheme)) ? url : ''
}

function parseInline(line) {
  const nodes = []
  let cursor = 0
  for (const match of line.matchAll(INLINE_RE)) {
    const [whole, bold, label, href] = match
    if (match.index > cursor) {
      nodes.push({ type: 'text', value: line.slice(cursor, match.index) })
    }
    if (bold !== undefined) {
      nodes.push({ type: 'bold', value: bold })
    } else {
      const url = safeHref(href)
      if (url) nodes.push({ type: 'link', value: label, href: url })
      else nodes.push({ type: 'text', value: whole })
    }
    cursor = match.index + whole.length
  }
  if (cursor < line.length) nodes.push({ type: 'text', value: line.slice(cursor) })
  return nodes
}
