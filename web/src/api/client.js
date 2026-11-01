const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'

let csrfToken = ''
let unauthorizedHandler = null

export class ApiError extends Error {
  constructor(message, code, status) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
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
    throw new ApiError('网络异常，请确认后端服务已启动', 'NETWORK_ERROR', 0)
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
      payload?.message || response.statusText || '请求失败',
      payload?.code || 'HTTP_ERROR',
      response.status,
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

export function errorMessage(error, fallback = '操作失败') {
  if (error instanceof ApiError) return error.message
  return error?.message || fallback
}
