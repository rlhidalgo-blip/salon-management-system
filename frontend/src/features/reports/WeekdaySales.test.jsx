// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import WeekdaySales from './WeekdaySales.jsx'
import { manilaToday } from './businessDates.js'

const names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const rows = names.map((weekday, index) => ({
  weekday_number: index + 1, weekday, gross_sales: '0.00', historical_gross_sales: '0.00',
  verified_open_gross_sales: '0.00', provisional_today_gross_sales: '0.00',
  verified_open_days: 0, verified_closed_days: 0, unknown_days: 0,
  unconfirmed_planned_days: 0, closed_dates_with_sales: 0,
  average_gross_per_verified_open_day: null,
}))
const report = {
  from: '2026-10-01', through: '2026-10-28', as_of: '2026-11-05T12:00:00+00:00',
  coverage: { historical_days: 28, verified_open_days: 1, verified_closed_days: 1,
    unknown_days: 2, unconfirmed_planned_days: 1, unverified_days: 3,
    closed_dates_with_sales: 1, incomplete_coverage: true },
  weekdays: rows.map((row, index) => index === 0 ? { ...row, gross_sales: '1234.50',
    historical_gross_sales: '1200.00', verified_open_gross_sales: '1000.00',
    provisional_today_gross_sales: '34.50', verified_open_days: 1, verified_closed_days: 1,
    unknown_days: 2, unconfirmed_planned_days: 1, closed_dates_with_sales: 1,
    average_gross_per_verified_open_day: '1000.00' } : row),
}
const reply = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body })

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

function setup(handler = () => reply(200, report)) {
  fetch.mockImplementation((url, options) => Promise.resolve(handler(url, options)))
  const onRevalidateSession = vi.fn().mockResolvedValue(true)
  render(<WeekdaySales onRevalidateSession={onRevalidateSession} />)
  return onRevalidateSession
}

it('shows seven ordered weekdays, distinct gross and average values, and a null average', async () => {
  setup()
  const chart = await screen.findByRole('figure', { name: 'Average gross sales per verified Open day' })
  expect(within(chart).getByText('₱1,000.00')).toBeTruthy()
  expect(within(chart).getAllByText('Unavailable')).toHaveLength(6)
  expect(chart.querySelectorAll('.weekday-chart-bar')).toHaveLength(1)
  const table = await screen.findByRole('table')
  const bodyRows = within(table).getAllByRole('row').slice(1)
  expect(bodyRows.map((row) => within(row).getByRole('rowheader').textContent)).toEqual(names)
  const monday = bodyRows[0]
  expect(within(monday).getByText('₱1,234.50')).toBeTruthy()
  expect(within(monday).getByText('₱1,200.00')).toBeTruthy()
  expect(within(monday).getAllByText('₱1,000.00')).toHaveLength(2)
  expect(within(monday).getByText('₱34.50')).toBeTruthy()
  expect(within(bodyRows[1]).getByText('Unavailable')).toBeTruthy()
  expect(fetch.mock.calls[0][1]).toMatchObject({ credentials: 'same-origin' })
  expect(screen.getByLabelText('7% of historical dates verified')).toBeTruthy()
  expect(within(screen.getByLabelText('Operating date coverage')).getByText('Unconfirmed plans')).toBeTruthy()
})

it('shows partial coverage, unconfirmed plans, provisional sales, and Closed anomalies', async () => {
  setup()
  expect(await screen.findByText(/Partial averages: 3 historical dates are unverified/)).toBeTruthy()
  expect(screen.getByText(/1 verified Closed dates contain completed sales/)).toBeTruthy()
  expect(screen.getByText(/Today’s completed sales are provisional/)).toBeTruthy()
  expect(screen.getByText(/Period: 2026-10-01 through 2026-10-28/)).toBeTruthy()
})

it('shows zero-data and no-denominator states', async () => {
  setup(() => reply(200, { ...report, coverage: { ...report.coverage,
    verified_open_days: 0, verified_closed_days: 0, unknown_days: 0,
    unconfirmed_planned_days: 0, unverified_days: 0, closed_dates_with_sales: 0,
    incomplete_coverage: false }, weekdays: rows }))
  expect(await screen.findByText('No verified Open historical dates are available for an average.')).toBeTruthy()
  expect(screen.queryByText(/Partial averages:/)).toBeNull()
  expect(within(screen.getByRole('table')).getAllByText('Unavailable')).toHaveLength(7)
  expect(within(screen.getByRole('figure')).getAllByText('Unavailable')).toHaveLength(7)
  expect(screen.getByText('Averages are not available yet')).toBeTruthy()
})

it('validates bounded Manila dates before fetching', async () => {
  setup()
  await screen.findByRole('table')
  const count = fetch.mock.calls.length
  fireEvent.change(screen.getByLabelText('From'), { target: { value: '2020-01-01' } })
  fireEvent.click(screen.getByRole('button', { name: 'Show weekdays' }))
  expect(screen.getByText('Choose 1 to 366 valid dates, ending no later than today in Manila.')).toBeTruthy()
  expect(fetch.mock.calls).toHaveLength(count)
  expect(screen.getByLabelText('Through').max).toBe(manilaToday())
})

it('loads, reports error, and retries without stale financial values', async () => {
  let count = 0
  setup(() => ++count === 1 ? reply(500, {}) : reply(200, report))
  expect(screen.getByText('Loading weekday sales…')).toBeTruthy()
  expect(await screen.findByText('Weekday analytics are temporarily unavailable. Please try again.')).toBeTruthy()
  expect(screen.queryByRole('table')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByRole('table')).toBeTruthy()
})

it('handles Cashier denial and expired sessions', async () => {
  const revalidate = setup(() => reply(403, {}))
  expect(await screen.findByText('You do not have permission to view weekday analytics.')).toBeTruthy()
  expect(revalidate).not.toHaveBeenCalled()
})

it('revalidates a 401 without showing financial data', async () => {
  const revalidate = setup(() => reply(401, {}))
  await waitFor(() => expect(revalidate).toHaveBeenCalledOnce())
  expect(screen.queryByRole('table')).toBeNull()
})
