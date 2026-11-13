<script>
import { h } from 'vue'

import { parseRichText } from '@/utils/richText'

//: 用 render 函数按解析结果造节点，不引入 v-html：公告内容永远只是文本与链接。
function renderChild(child, index) {
  if (child.type === 'br') return h('br', { key: index })
  if (child.type === 'bold') return h('strong', { key: index }, child.value)
  if (child.type === 'link') {
    const external = !child.href.toLowerCase().startsWith('mailto:')
    return h(
      'a',
      {
        key: index,
        href: child.href,
        target: external ? '_blank' : undefined,
        rel: external ? 'noopener noreferrer' : undefined,
      },
      child.value,
    )
  }
  return child.value
}

export default {
  name: 'RichText',
  props: { text: { type: String, default: '' } },
  setup(props) {
    return () =>
      h(
        'div',
        { class: 'rich-text' },
        parseRichText(props.text).map((block, index) =>
          h('p', { key: index }, block.children.map(renderChild)),
        ),
      )
  },
}
</script>
