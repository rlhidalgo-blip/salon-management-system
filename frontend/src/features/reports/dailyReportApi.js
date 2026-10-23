const URL = '/api/v1/reports/daily'

export class DailyReportApiError extends Error {
  constructor(status = 0) {
    super('Daily report request failed')
    this.status = status
  }
}

export async function getDailyReport(businessDate = '', signal) {
  const path = businessDate ? `${URL}?${new URLSearchParams({ business_date: businessDate })}` : URL
  let response
  try {
    response = await fetch(path, { credentials: 'same-origin', signal })
  } catch {
    throw new DailyReportApiError()
  }
  if (!response.ok) throw new DailyReportApiError(response.status)
  try {
    return await response.json()
  } catch {
    throw new DailyReportApiError()
  }
}
