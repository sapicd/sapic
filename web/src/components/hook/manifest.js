//: config_schema 与节点词表共用同一套字段结构，直接包进 fieldset 复用渲染器。
export function manifestNodes(manifest) {
  const children = []

  if (manifest.description) {
    children.push({ type: 'text', text: manifest.description, muted: true })
  }
  children.push(...(manifest.config_schema || []).map((field) => ({ ...field })))

  const actions = (manifest.actions || []).map((action) => ({
    type: 'button',
    text: action.label || action.name,
    action: action.name,
    with_form: Boolean(action.with_form),
    confirm: Boolean(action.confirm),
    variant: action.danger ? 'danger' : 'primary',
  }))
  if (actions.length) {
    children.push({ type: 'group', children: actions })
  }

  return [
    {
      type: 'fieldset',
      legend: manifest.title,
      status: manifest.version ? `v${manifest.version}` : undefined,
      children,
    },
  ]
}
