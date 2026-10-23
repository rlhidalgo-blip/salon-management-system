const BASE = '/api/v1/transactions'

export class TransactionHistoryApiError extends Error {
  constructor(status = 0) {
    super('Transaction history request failed')
    this.status = status
  }
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${BASE}${path}`, { credentials: 'same-origin', ...options })
  } catch {
    throw new TransactionHistoryApiError()
  }
  if (!response.ok) throw new TransactionHistoryApiError(response.status)
  try {
    return await response.json()
  } catch {
    throw new TransactionHistoryApiError()
  }
}

export function getTransactionHistory({ businessDate, cursor, signal }) {
  const params = new URLSearchParams({ limit: '50' })
  if (businessDate) params.set('business_date', businessDate)
  if (cursor) params.set('cursor', cursor)
  return request(`?${params}`, { signal })
}

export function getTransactionDetail(id, signal) {
  return request(`/${encodeURIComponent(id)}`, { signal })
}

export function voidTransaction(id, reason, csrfToken) {
  return request(`/${encodeURIComponent(id)}/void`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ reason }),
  })
}
