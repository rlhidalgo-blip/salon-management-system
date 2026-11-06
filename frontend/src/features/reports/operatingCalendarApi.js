const BASE = '/api/v1/operating-days'

export class OperatingCalendarApiError extends Error {
  constructor(status = 0, code = '') {
    super('Operating calendar request failed')
    this.status = status
    this.code = code
  }
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${BASE}${path}`, { credentials: 'same-origin', ...options })
  } catch {
    throw new OperatingCalendarApiError()
  }
  if (!response.ok) {
    let code = ''
    try { code = (await response.json()).error?.code || '' } catch { /* Keep the status. */ }
    throw new OperatingCalendarApiError(response.status, code)
  }
  try { return await response.json() } catch { throw new OperatingCalendarApiError() }
}

export function getOperatingDays(from, through, signal) {
  return request(`?${new URLSearchParams({ from, through })}`, { signal })
}

export function getOperatingDayHistory(day, signal) {
  return request(`/${encodeURIComponent(day)}/history`, { signal })
}

export function putOperatingDay(day, status, closureReason, expectedVersion, csrfToken) {
  return request(`/${encodeURIComponent(day)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ status, closure_reason: closureReason, expected_version: expectedVersion }),
  })
}

export function bulkVerifyOpen(dates, csrfToken) {
  return request('/bulk-verify-open', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ dates }),
  })
}
