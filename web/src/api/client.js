import { t } from '@/i18n'

import { localizeMessage } from './messages'

const API_BASE = import.meta.env.VITE_API_BASE || '/api/v2'

let csrfToken = ''
let unauthorizedHandler = null

export class ApiError extends Error {
  constructor(message, code, status, requestId = '') {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    //: 后端每个响应都带 request_id，5xx 时展示出来才能对着 sys.log 查原因。
    this.requestId = requestId
  }
}

export function setCsrfToken(token) {
  csrfToken = token || ''
}

export function onUnauthorized(handler) {
  unauthorizedHandler = handler
}

function buildUrl(path, query) {
  const url = new URL(`${API_BASE}${path}`, window.location.origin)
  Object.entries(query || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value))
    }
  })
  return url.toString()
}

async function request(method, path, options = {}) {
  const { json, form, query } = options
  const headers = {}
  const init = { method, headers, credentials: 'include' }

  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(json)
  } else if (form) {
    init.body = form
  }
  if (!['GET', 'HEAD'].includes(method) && csrfToken) {
    headers['X-CSRF-Token'] = csrfToken
  }

  let response
  try {
    response = await fetch(buildUrl(path, query), init)
  } catch (error) {
    throw new ApiError(t('errors.network'), 'NETWORK_ERROR', 0)
  }

  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json')
    ? await response.json()
    : null

  if (!response.ok) {
    if (response.status === 401 && unauthorizedHandler) {
      unauthorizedHandler()
    }
    throw new ApiError(
      payload?.message || response.statusText || t('errors.http'),
      payload?.code || 'HTTP_ERROR',
      response.status,
      payload?.request_id || response.headers.get('X-Request-Id') || '',
    )
  }
  return payload ? payload.data : null
}

export const api = {
  get: (path, options) => request('GET', path, options),
  post: (path, options) => request('POST', path, options),
  put: (path, options) => request('PUT', path, options),
  patch: (path, options) => request('PATCH', path, options),
  del: (path, options) => request('DELETE', path, options),
}

export function errorMessage(error, fallback = t('errors.operation')) {
  //: ApiError.message 保留后端英文原文（排查用），展示前按当前语言转换。
  const message =
    error instanceof ApiError
      ? localizeMessage(error.message, error.code) || fallback
      : localizeMessage(error?.message) || fallback
  //: 服务端 5xx 的原因只会写在 sys.log 里，附上请求 ID 才能对上那一行。
  if (error instanceof ApiError && error.requestId && error.status >= 500) {
    return `${message}${t('errors.requestId', { id: error.requestId })}`
  }
  return message
}
