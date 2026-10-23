// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import MonthlyFinancialSummary from './MonthlyFinancialSummary.jsx'

const report = {
  reporting_month: '2026-10', gross_sales: '2472.25', cash_sales: '1000.00',
  gcash_sales: '1472.25', total_staff_commission: '1161.00', total_business_share: '1311.25',
  completed_transaction_count: 6, voided_transaction_count: 2,
  unassigned_product_sales: '250.00',
  staff_performance: [{ staff_id: 7, current_staff_name: 'Current Inactive Stylist',
    attributed_sales: '2222.25', total_staff_commission: '1161.00' }],
}
const reply = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
const deferred = () => {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

function setup(handler = () => reply(200, report)) {
  fetch.mockImplementation((url, options) => Promise.resolve(handler(url, options)))
  const onRevalidateSession = vi.fn().mockResolvedValue(true)
  render(<MonthlyFinancialSummary onRevalidateSession={onRevalidateSession} />)
  return onRevalidateSession
}

it('shows server monetary values and staff performance without unassigned sales or counts', async () => {
  setup()
  expect(await screen.findByRole('heading', { name: 'Monthly Financial Summary' })).toBeTruthy()
  expect(await screen.findByText('Current Inactive Stylist')).toBeTruthy()
  expect(screen.getByText('October 2026').classList.contains('monthly-report-date')).toBe(true)
  const totals = document.querySelector('.monthly-report-totals')
  expect(totals.children).toHaveLength(3)
  expect(within(totals).getByText('₱2,472.25')).toBeTruthy()
  expect(within(totals).getByText('₱1,161.00')).toBeTruthy()
  expect(within(totals).getByText('₱1,311.25')).toBeTruthy()
  expect(screen.getByText('₱1,000.00')).toBeTruthy()
  expect(screen.getByText('₱1,472.25')).toBeTruthy()
  const lower = document.querySelector('.monthly-report-lower')
  expect(lower.children).toHaveLength(2)
  expect(lower.children[0].classList.contains('monthly-report-payment')).toBe(true)
  expect(lower.children[1].classList.contains('monthly-report-staff')).toBe(true)
  const staff = screen.getByRole('region', { name: 'Staff Performance' })
  expect(within(staff).getAllByRole('columnheader').map((header) => header.textContent))
    .toEqual(['Staff', 'Sales', 'Commission'])
  expect(within(staff).getByRole('row', { name: /Current Inactive Stylist/ }).children).toHaveLength(3)
  expect(within(staff).getByText('₱2,222.25')).toBeTruthy()
  expect(screen.queryByText('₱250.00')).toBeNull()
  expect(screen.queryByText(/Unassigned Product Sales|Completed|Voided/)).toBeNull()
  const refresh = screen.getByRole('button', { name: 'Refresh monthly report' })
  expect(refresh.textContent).toBe('')
  expect(refresh.querySelector('svg[data-icon="refresh"][aria-hidden="true"]')).toBeTruthy()
  expect(fetch.mock.calls[0][0]).toBe('/api/v1/reports/monthly')
  expect(fetch.mock.calls[0][1]).toMatchObject({ credentials: 'same-origin' })
  expect(fetch.mock.calls[0][1].headers).toBeUndefined()
})

it('selects a historical month, blocks future values, returns to server default, and refreshes', async () => {
  setup((url) => reply(200, { ...report, reporting_month: url.includes('month=2025-09') ? '2025-09' : '2026-10' }))
  await screen.findByText('Current Inactive Stylist')
  const selector = screen.getByLabelText('Reporting month')
  expect(selector.getAttribute('type')).toBe('month')
  fireEvent.change(selector, { target: { value: '2025-09' } })
  await waitFor(() => expect(fetch.mock.calls.at(-1)[0]).toBe('/api/v1/reports/monthly?month=2025-09'))
  expect(await screen.findByText('September 2025')).toBeTruthy()
  const count = fetch.mock.calls.length
  const max = selector.max
  const [year, month] = max.split('-').map(Number)
  const future = month === 12 ? `${year + 1}-01` : `${year}-${String(month + 1).padStart(2, '0')}`
  fireEvent.change(selector, { target: { value: future } })
  expect(fetch.mock.calls).toHaveLength(count)
  expect(selector.value).toBe('2025-09')
  fireEvent.click(screen.getByRole('button', { name: 'Refresh monthly report' }))
  await waitFor(() => expect(fetch.mock.calls).toHaveLength(count + 1))
  expect(fetch.mock.calls.at(-1)[0]).toBe('/api/v1/reports/monthly?month=2025-09')
  fireEvent.change(selector, { target: { value: '' } })
  await waitFor(() => expect(fetch.mock.calls.at(-1)[0]).toBe('/api/v1/reports/monthly'))
})

it('disables refresh while loading and shows zero-data months', async () => {
  const pending = deferred()
  fetch.mockImplementation(() => pending.promise)
  render(<MonthlyFinancialSummary onRevalidateSession={vi.fn().mockResolvedValue(true)} />)
  const refresh = screen.getByRole('button', { name: 'Refresh monthly report' })
  expect(refresh.disabled).toBe(true)
  expect(refresh.getAttribute('aria-busy')).toBe('true')
  await act(async () => pending.resolve(reply(200, { ...report, gross_sales: '0.00',
    cash_sales: '0.00', gcash_sales: '0.00', total_staff_commission: '0.00',
    total_business_share: '0.00', completed_transaction_count: 0, voided_transaction_count: 0,
    unassigned_product_sales: '0.00', staff_performance: [] })))
  expect(refresh.disabled).toBe(false)
  expect(screen.getByText('No staff performance for this month.')).toBeTruthy()
  expect(within(document.querySelector('.monthly-report-totals')).getAllByText('₱0.00')).toHaveLength(3)
})

it('clears stale totals after a failed refresh and retries', async () => {
  let calls = 0
  setup(() => ++calls === 1 ? reply(200, report)
    : calls === 2 ? reply(500, {}) : reply(200, { ...report, gross_sales: '10.00' }))
  await screen.findByText('Current Inactive Stylist')
  fireEvent.click(screen.getByRole('button', { name: 'Refresh monthly report' }))
  expect(await screen.findByText('Monthly report is temporarily unavailable. Please try again.')).toBeTruthy()
  expect(screen.queryByText('₱2,472.25')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByText('₱10.00')).toBeTruthy()
})

it.each([
  [403, 'You do not have permission to view monthly reports.'],
  [422, 'Choose a valid current or historical month.'],
])('handles HTTP %s without showing financial data', async (status, message) => {
  setup(() => reply(status, {}))
  expect(await screen.findByText(message)).toBeTruthy()
  expect(screen.queryByText('₱2,472.25')).toBeNull()
})

it('revalidates 401 and keeps financial data hidden', async () => {
  const revalidate = setup(() => reply(401, {}))
  await waitFor(() => expect(revalidate).toHaveBeenCalledTimes(1))
  expect(screen.queryByText('₱2,472.25')).toBeNull()
})

it('handles network failure with retry', async () => {
  fetch.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(reply(200, report))
  render(<MonthlyFinancialSummary onRevalidateSession={vi.fn().mockResolvedValue(true)} />)
  expect(await screen.findByText('Monthly report is temporarily unavailable. Please try again.')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByText('Current Inactive Stylist')).toBeTruthy()
})

it('ignores a superseded month response', async () => {
  const old = deferred()
  fetch.mockImplementation((url) => url.includes('month=2025-09') ? old.promise
    : Promise.resolve(reply(200, { ...report, reporting_month: '2025-10', gross_sales: '21.00' })))
  render(<MonthlyFinancialSummary onRevalidateSession={vi.fn().mockResolvedValue(true)} />)
  const selector = screen.getByLabelText('Reporting month')
  fireEvent.change(selector, { target: { value: '2025-09' } })
  await waitFor(() => expect(fetch.mock.calls.at(-1)[0]).toContain('2025-09'))
  fireEvent.change(selector, { target: { value: '2025-10' } })
  expect(await screen.findByText('₱21.00')).toBeTruthy()
  await act(async () => old.resolve(reply(200, report)))
  expect(screen.queryByText('₱2,472.25')).toBeNull()
})

it('refreshes the default month on focus after a Manila month change', async () => {
  setup()
  await screen.findByText('Current Inactive Stylist')
  const initial = fetch.mock.calls.length
  vi.useFakeTimers()
  vi.setSystemTime(new Date(Date.now() + 35 * 24 * 60 * 60 * 1000))
  await act(async () => { fireEvent.focus(window) })
  expect(fetch.mock.calls.length).toBe(initial + 1)
  expect(fetch.mock.calls.at(-1)[0]).toBe('/api/v1/reports/monthly')
})
