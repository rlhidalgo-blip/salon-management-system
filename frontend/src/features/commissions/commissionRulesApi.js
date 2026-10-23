const RULES_URL = '/api/v1/commission-rules'

export class CommissionRulesApiError extends Error {
  constructor(status = 0) {
    super('Commission rules request failed')
    this.status = status
  }
}

async function request(path = '', options = {}) {
  const response = await fetch(`${RULES_URL}${path}`, {
    credentials: 'same-origin',
    ...options,
  })
  if (!response.ok) throw new CommissionRulesApiError(response.status)
  return response.json()
}

export function getCommissionRules(signal) {
  return request('', { signal })
}

export function createCommissionRule(name, type, value, csrfToken) {
  return request('', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ name, type, value }),
  })
}

export function changeCommissionRuleStatus(id, active, csrfToken) {
  return request(`/${id}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ active }),
  })
}
