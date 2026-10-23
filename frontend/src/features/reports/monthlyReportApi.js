const URL = '/api/v1/reports/monthly'

export class MonthlyReportApiError extends Error {
  constructor(status = 0) {
    super('Monthly report request failed')
    this.status = status
  }
}

export async function getMonthlyReport(month = '', signal) {
  const path = month ? `${URL}?${new URLSearchParams({ month })}` : URL
  let response
  try {
    response = await fetch(path, { credentials: 'same-origin', signal })
  } catch {
    throw new MonthlyReportApiError()
  }
  if (!response.ok) throw new MonthlyReportApiError(response.status)
  try {
    return await response.json()
  } catch {
    throw new MonthlyReportApiError()
  }
}
