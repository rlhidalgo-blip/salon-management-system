const BASE = '/api/v1'

export class SalesApiError extends Error {
  constructor(status = 0) {
    super('Sales request failed')
    this.status = status
  }
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${BASE}${path}`, { credentials: 'same-origin', ...options })
  } catch {
    throw new SalesApiError()
  }
  if (!response.ok) throw new SalesApiError(response.status)
  try {
    return await response.json()
  } catch {
    throw new SalesApiError()
  }
}

export function getSalesOptions(signal) {
  return request('/sales/options', { signal })
}

export function getManualSalesOptions(signal) {
  return request('/sales/manual-options', { signal })
}

export function createSale(payload, key, csrfToken) {
  return request('/transactions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key, 'X-CSRF-Token': csrfToken },
    body: JSON.stringify(payload),
  })
}

export function createManualSale(payload, key, csrfToken) {
  return request('/transactions/manual', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key, 'X-CSRF-Token': csrfToken },
    body: JSON.stringify(payload),
  })
}

export function getSaleStatus(key) {
  return request(`/transactions/by-idempotency-key/${encodeURIComponent(key)}`)
}
