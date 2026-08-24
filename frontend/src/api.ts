const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const TOKEN_KEY = 'pulse-hr-access-token'

export function getAccessToken() {
  return window.sessionStorage.getItem(TOKEN_KEY)
}

export function setAccessToken(token: string) {
  window.sessionStorage.setItem(TOKEN_KEY, token)
}

export function clearAccessToken() {
  window.sessionStorage.removeItem(TOKEN_KEY)
}

function getErrorMessage(body: unknown, status: number) {
  if (!body || typeof body !== 'object' || !('detail' in body)) {
    return `请求失败（${status}）`
  }
  const detail = (body as { detail?: unknown }).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== 'object') return String(item)
        const message = 'msg' in item ? String(item.msg) : '输入内容不符合要求'
        return message.replace(/^Value error,\s*/i, '')
      })
      .filter(Boolean)
    if (messages.length) return messages.join('；')
  }
  return `请求失败（${status}）`
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getAccessToken()
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 401 && !path.endsWith('/auth/login')) {
      clearAccessToken()
      window.dispatchEvent(new CustomEvent('hr-auth-expired'))
    }
    throw new Error(getErrorMessage(body, response.status))
  }
  return body as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
}
