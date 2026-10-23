// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import DailyFinancialSummary from './DailyFinancialSummary.jsx'

const owner = { id: 1, username: 'synthetic_owner', role: 'Owner' }
const cashier = { id: 2, username: 'synthetic_cashier', role: 'Cashier' }
const report = {
  business_date: '2026-10-23', gross_sales: '2472.00', cash_sales: '1000.00',
  gcash_sales: '1472.00', total_staff_commission: '1161.00', total_business_share: '1311.00',
  completed_transaction_count: 6, voided_transaction_count: 2,
  staff_commissions: [{ staff_id: 7, current_staff_name: 'Current Inactive Stylist',
    total_staff_commission: '1161.00' }],
}
const reply = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
const deferred = () => {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

function setup(user = owner, handler = () => reply(200, report)) {
  fetch.mockImplementation((url, options) => Promise.resolve(handler(url, options)))
  const onRevalidateSession = vi.fn().mockResolvedValue(true)
  render(<DailyFinancialSummary user={user} onRevalidateSession={onRevalidateSession} />)
  return onRevalidateSession
}

it('shows backend financial totals and simplified Staff rows without transaction counts', async () => {
  setup()
  const summary = await screen.findByRole('heading', { name: 'Daily Financial Summary' })
  expect(summary).toBeTruthy()
  expect(await screen.findByText('Current Inactive Stylist')).toBeTruthy()
  const staff = screen.getByRole('region', { name: 'Staff Commissions' })
  expect(within(staff).getAllByRole('heading')).toHaveLength(1)
  expect(within(staff).getByRole('listitem').textContent).toBe('Current Inactive Stylist₱1,161.00')
  expect(within(staff).queryByText('Current Staff Name')).toBeNull()
  expect(within(staff).queryByText('Staff Commission')).toBeNull()
  expect(screen.queryByText(/historical name snapshots/)).toBeNull()
  const totals = document.querySelector('.daily-report-totals')
  expect(within(totals).getByText('₱2,472.00')).toBeTruthy()
  expect(within(totals).getByText('₱1,161.00')).toBeTruthy()
  expect(within(totals).getByText('₱1,311.00')).toBeTruthy()
  expect(screen.getByText('₱1,000.00')).toBeTruthy()
  expect(screen.getByText('₱1,472.00')).toBeTruthy()
  expect(screen.queryByRole('heading', { name: 'Transactions' })).toBeNull()
  expect(screen.queryByText('Completed')).toBeNull()
  expect(screen.queryByText('Voided')).toBeNull()
  expect(screen.queryByText(/Completed sales and staff commissions/)).toBeNull()
  expect(screen.getByText('October 23, 2026')).toBeTruthy()
  const refresh = screen.getByRole('button', { name: 'Refresh report' })
  expect(refresh.textContent).toBe('')
  expect(refresh.querySelector('svg[data-icon="refresh"][aria-hidden="true"]')).toBeTruthy()
  expect(refresh.disabled).toBe(false)
  expect(fetch.mock.calls[0][0]).toBe('/api/v1/reports/daily')
  expect(fetch.mock.calls[0][1]).toMatchObject({ credentials: 'same-origin' })
  expect(fetch.mock.calls[0][1].headers).toBeUndefined()
})

it('lets Owner choose historical dates, return to server today, and refresh', async () => {
  setup(owner, (url) => reply(200, { ...report, business_date: url.includes('business_date=')
    ? '2026-10-20' : '2026-10-23' }))
  await screen.findByText('Current Inactive Stylist')
  const date = screen.getByLabelText('Business date')
  fireEvent.change(date, { target: { value: '2026-10-20' } })
  await waitFor(() => expect(fetch.mock.calls.at(-1)[0]).toBe('/api/v1/reports/daily?business_date=2026-10-20'))
  await screen.findByText('October 20, 2026')
  fireEvent.click(screen.getByRole('button', { name: 'Refresh report' }))
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3))
  fireEvent.change(date, { target: { value: '' } })
  await waitFor(() => expect(fetch.mock.calls.at(-1)[0]).toBe('/api/v1/reports/daily'))
})

it('keeps Cashier on server-defined today without a date picker', async () => {
  setup(cashier)
  await screen.findByText('Current Inactive Stylist')
  expect(screen.queryByLabelText('Business date')).toBeNull()
  expect(fetch.mock.calls[0][0]).toBe('/api/v1/reports/daily')
  expect(screen.getByText('October 23, 2026')).toBeTruthy()
  expect(screen.queryByText(/Manila today/)).toBeNull()
  const staff = screen.getByRole('region', { name: 'Staff Commissions' })
  expect(within(staff).getByRole('listitem').textContent).toBe('Current Inactive Stylist₱1,161.00')
  expect(within(staff).queryByRole('table')).toBeNull()
})

it('keeps the icon-only refresh control accessible and disabled while loading', async () => {
  const pending = deferred()
  fetch.mockImplementation(() => pending.promise)
  render(<DailyFinancialSummary user={cashier} onRevalidateSession={vi.fn().mockResolvedValue(true)} />)
  const refresh = screen.getByRole('button', { name: 'Refresh report' })
  expect(refresh.textContent).toBe('')
  expect(refresh.disabled).toBe(true)
  expect(refresh.getAttribute('aria-busy')).toBe('true')
  await act(async () => pending.resolve(reply(200, report)))
  expect(refresh.disabled).toBe(false)
  expect(refresh.getAttribute('aria-busy')).toBe('false')
})

it('shows zero totals and a useful empty state', async () => {
  setup(owner, () => reply(200, { ...report, gross_sales: '0.00', cash_sales: '0.00',
    gcash_sales: '0.00', total_staff_commission: '0.00', total_business_share: '0.00',
    completed_transaction_count: 0, voided_transaction_count: 1, staff_commissions: [] }))
  expect(await screen.findByText('No staff commissions for this date.')).toBeTruthy()
  expect(screen.getByText('No completed sales for this date. Financial totals are zero.')).toBeTruthy()
  expect(within(document.querySelector('.daily-report-totals')).getAllByText('₱0.00')).toHaveLength(3)
})

it('does not show stale totals after a failed refresh and can retry', async () => {
  let calls = 0
  setup(owner, () => ++calls === 1 ? reply(200, report)
    : calls === 2 ? reply(500, {}) : reply(200, { ...report, gross_sales: '10.00' }))
  await screen.findByText('Current Inactive Stylist')
  fireEvent.click(screen.getByRole('button', { name: 'Refresh report' }))
  expect(await screen.findByText('Daily report is temporarily unavailable. Please try again.')).toBeTruthy()
  expect(screen.queryByText('₱2,472.00')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByText('₱10.00')).toBeTruthy()
})

it.each([
  [403, 'You do not have permission to view this report date.'],
  [422, 'Choose a valid current or historical business date.'],
])('handles HTTP %s as a clear report error', async (status, message) => {
  setup(owner, () => reply(status, {}))
  expect(await screen.findByText(message)).toBeTruthy()
  expect(screen.queryByText('₱2,472.00')).toBeNull()
})

it('revalidates a 401 session and leaves the report hidden', async () => {
  const revalidate = setup(owner, () => reply(401, {}))
  await waitFor(() => expect(revalidate).toHaveBeenCalledTimes(1))
  expect(screen.queryByText('₱2,472.00')).toBeNull()
})

it('handles network failures with a retry option', async () => {
  fetch.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(reply(200, report))
  const onRevalidateSession = vi.fn().mockResolvedValue(true)
  render(<DailyFinancialSummary user={owner} onRevalidateSession={onRevalidateSession} />)
  expect(await screen.findByText('Daily report is temporarily unavailable. Please try again.')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByText('Current Inactive Stylist')).toBeTruthy()
})

it('ignores an older date response when a newer date was selected', async () => {
  const old = deferred()
  fetch.mockImplementation((url) => url.includes('2026-10-20') ? old.promise
    : Promise.resolve(reply(200, { ...report, business_date: '2026-10-21', gross_sales: '21.00' })))
  render(<DailyFinancialSummary user={owner} onRevalidateSession={vi.fn().mockResolvedValue(true)} />)
  const date = screen.getByLabelText('Business date')
  fireEvent.change(date, { target: { value: '2026-10-20' } })
  await waitFor(() => expect(fetch.mock.calls.at(-1)[0]).toContain('2026-10-20'))
  fireEvent.change(date, { target: { value: '2026-10-21' } })
  expect(await screen.findByText('₱21.00')).toBeTruthy()
  await act(async () => old.resolve(reply(200, { ...report, business_date: '2026-10-20' })))
  expect(screen.queryByText('₱2,472.00')).toBeNull()
})

it('refreshes the default Manila day on focus after midnight', async () => {
  setup(cashier)
  await screen.findByText('Current Inactive Stylist')
  const initial = fetch.mock.calls.length
  vi.useFakeTimers()
  vi.setSystemTime(new Date(Date.now() + 24 * 60 * 60 * 1000))
  await act(async () => { fireEvent.focus(window) })
  expect(fetch.mock.calls.length).toBe(initial + 1)
  expect(fetch.mock.calls.at(-1)[0]).toBe('/api/v1/reports/daily')
})
