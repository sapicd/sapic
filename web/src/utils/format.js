//: 后端时间统一是 10 位 int 时间戳，"秒"与"毫秒"都要能解析。
function toDate(value) {
  const number = Number(value)
  if (!number) return null
  return new Date(number < 1e12 ? number * 1000 : number)
}

export function formatTime(value) {
  const date = toDate(value)
  return date ? date.toLocaleString() : '-'
}

export function formatSize(bytes) {
  const number = Number(bytes) || 0
  if (number < 1024) return `${number} B`
  if (number < 1024 * 1024) return `${(number / 1024).toFixed(1)} KB`
  return `${(number / 1024 / 1024).toFixed(1)} MB`
}

export function absoluteUrl(url) {
  if (!url) return ''
  return new URL(url, window.location.origin).toString()
}
