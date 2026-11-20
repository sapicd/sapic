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

//: 表格里用的紧凑时间：固定 YYYY/MM/DD HH:mm，秒不占宽，列宽可预期。
export function formatShortTime(value) {
  const date = toDate(value)
  if (!date) return '-'
  const pad = (number) => String(number).padStart(2, '0')
  const day = `${date.getFullYear()}/${pad(date.getMonth() + 1)}/${pad(date.getDate())}`
  return `${day} ${pad(date.getHours())}:${pad(date.getMinutes())}`
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
