const STAFF_URL = '/api/v1/staff'

export class StaffApiError extends Error {
  constructor(status = 0) {
    super('Staff request failed')
    this.status = status
  }
}

async function request(path = '', options = {}) {
  const response = await fetch(`${STAFF_URL}${path}`, {
    credentials: 'same-origin',
    ...options,
  })
  if (!response.ok) throw new StaffApiError(response.status)
  return response.json()
}

export function getStaff(signal) {
  return request('', { signal })
}

export function addStaff(name, role, csrfToken) {
  return request('', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ name, role }),
  })
}

export function changeStaffStatus(id, active, csrfToken) {
  return request(`/${id}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ active }),
  })
}
