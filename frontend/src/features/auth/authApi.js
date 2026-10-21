const AUTH_URL = '/api/v1/auth'

export class AuthApiError extends Error {
  constructor(status = 0) {
    super('Authentication request failed')
    this.status = status
  }
}

async function request(path, options = {}) {
  const response = await fetch(`${AUTH_URL}${path}`, {
    credentials: 'same-origin',
    ...options,
  })

  if (!response.ok) throw new AuthApiError(response.status)
  if (response.status === 204) return null

  const body = await response.json()
  if (!body?.user || typeof body.csrf_token !== 'string') throw new AuthApiError()
  return { user: body.user, csrfToken: body.csrf_token }
}

export function login(username, password) {
  return request('/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export function getCurrentUser(signal) {
  return request('/me', { signal })
}

export function logout(csrfToken) {
  return request('/logout', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
  })
}
