const URL = '/api/v1/reports/weekday-sales'

export class WeekdaySalesApiError extends Error {
  constructor(status = 0) {
    super('Weekday sales request failed')
    this.status = status
  }
}

export async function getWeekdaySales(from, through, signal) {
  let response
  try {
    response = await fetch(`${URL}?${new URLSearchParams({ from, through })}`, {
      credentials: 'same-origin', signal,
    })
  } catch {
    throw new WeekdaySalesApiError()
  }
  if (!response.ok) throw new WeekdaySalesApiError(response.status)
  try { return await response.json() } catch { throw new WeekdaySalesApiError() }
}
