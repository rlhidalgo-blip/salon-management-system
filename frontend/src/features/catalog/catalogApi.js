const BASE = '/api/v1'

export class CatalogApiError extends Error {
  constructor(status = 0) {
    super('Catalog request failed')
    this.status = status
  }
}

async function request(kind, path = '', options = {}) {
  const response = await fetch(`${BASE}/${kind}${path}`, { credentials: 'same-origin', ...options })
  if (!response.ok) throw new CatalogApiError(response.status)
  return response.json()
}

export function getCatalogItems(kind, signal) {
  return request(kind, '', { signal })
}

function write(kind, path, method, body, csrfToken) {
  return request(kind, path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify(body),
  })
}

export function createCatalogItem(kind, values, csrfToken) {
  return write(kind, '', 'POST', values, csrfToken)
}

export function updateCatalogItem(kind, id, values, csrfToken) {
  return write(kind, `/${id}`, 'PATCH', values, csrfToken)
}

export function changeCatalogItemStatus(kind, id, active, csrfToken) {
  return write(kind, `/${id}/status`, 'PATCH', { active }, csrfToken)
}
