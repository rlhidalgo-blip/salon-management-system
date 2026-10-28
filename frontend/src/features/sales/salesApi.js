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

export async function getSalesCapabilities(signal) {
  const result = await request('/sales/capabilities', { signal, cache: 'no-store' })
  if (!result || Object.keys(result).length !== 1 ||
      (result.protocol !== 'legacy' && result.protocol !== 'reserved_v1')) throw new SalesApiError()
  return result.protocol
}

export function getOpenSaleAttempt(signal) {
  return request('/sales/attempts/open', { signal, cache: 'no-store' })
}

export function getOwnSaleAttemptByKey(key, signal) {
  return request(`/sales/attempts/by-idempotency-key/${encodeURIComponent(key)}`,
    { signal, cache: 'no-store' })
}

export function findSaleAttempts(recordingUserId, reference, beforeId, signal) {
  const query = new URLSearchParams({ recording_user_id: String(recordingUserId), limit: '50' })
  if (reference) query.set('reference', reference)
  if (beforeId) query.set('before_id', String(beforeId))
  return request(`/sales/attempts?${query}`, { signal, cache: 'no-store' })
}

export function getSaleAttempt(attemptId, signal) {
  return request(`/sales/attempts/${attemptId}`, { signal, cache: 'no-store' })
}

export function cancelSaleAttempt(attemptId, reason, csrfToken) {
  return request(`/sales/attempts/${attemptId}/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ reason, evidence_verified: true }),
  })
}

export function reserveSaleAttempt(source, payload, key, csrfToken) {
  return request('/sales/attempts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key, 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ source, sale: payload }),
  })
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

export function getOwnerSaleStatus(recordingUserId, key) {
  return request(`/transactions/reconciliation/${recordingUserId}/${encodeURIComponent(key)}`)
}

export function acknowledgeOwnerSale(recordingUserId, key, csrfToken) {
  return request(`/transactions/reconciliation/${recordingUserId}/${encodeURIComponent(key)}/acknowledge`, {
    method: 'POST', headers: { 'X-CSRF-Token': csrfToken },
  })
}
