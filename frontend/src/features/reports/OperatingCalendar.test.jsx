// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import ReportsSection from './ReportsSection.jsx'
import OperatingCalendar from './OperatingCalendar.jsx'
import { manilaToday, monthBounds, shiftDate, shiftMonth } from './businessDates.js'

const today = manilaToday()
const month = today.slice(0, 7)
const yesterday = shiftDate(today, -1)
const older = shiftDate(today, -2)
const tomorrow = shiftDate(today, 1)
const day = (business_date, status = 'Unknown', extra = {}) => ({
  business_date, status, closure_reason: null, version: 0,
  completed_transaction_count: 0, gross_sales: '0.00', inconsistency: false, ...extra,
})
const reply = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
const error = (status, code) => reply(status, { error: { code } })
const revalidate = () => vi.fn().mockResolvedValue(true)

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.unstubAllEnvs() })

function renderCalendar(days, { writesEnabled = false, handler } = {}) {
  fetch.mockImplementation((url, options) => Promise.resolve(handler?.(url, options) ??
    (url.includes('/history') ? reply(200, []) : reply(200, days))))
  render(<OperatingCalendar csrfToken="csrf-test" onRevalidateSession={revalidate()}
    writesEnabled={writesEnabled} />)
}

function selectDate(date, status = 'Unknown') {
  fireEvent.click(screen.getByRole('button', { name: `${date}: ${status}` }))
}

it('navigates months and selects dates in a Monday-first calendar grid', async () => {
  fetch.mockImplementation((url) => {
    const params = new URL(url, 'http://localhost').searchParams
    return Promise.resolve(url.includes('/history') ? reply(200, []) : reply(200, [day(params.get('from'))]))
  })
  render(<OperatingCalendar onRevalidateSession={revalidate()} />)
  const grid = await screen.findByRole('group', { name: /operating dates/ })
  expect([...grid.querySelectorAll('.calendar-weekday')].map((item) => item.textContent))
    .toEqual(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'])
  const current = monthBounds(month)
  expect(fetch.mock.calls[0][0]).toContain(`from=${current.from}&through=${current.through}`)
  selectDate(current.from)
  expect(within(screen.getByLabelText(`Details for ${current.from}`)).getByText('Gross sales')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Previous month' }))
  const previous = monthBounds(shiftMonth(month, -1))
  await waitFor(() => expect(fetch.mock.calls.some(([url]) => url.includes(`from=${previous.from}&through=${previous.through}`))).toBe(true))
  expect(await screen.findByRole('button', { name: `${previous.from}: Unknown` })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Next month' }))
  expect(await screen.findByRole('group', { name: /operating dates/ })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Today' }))
  expect(screen.getByText(new RegExp(month.replace('-', '-')))).toBeTruthy()
})

it('shows four status indicators and actual selected-date details while write-gated', async () => {
  renderCalendar([
    day(older, 'Open'), day(yesterday, 'Closed', { closure_reason: 'Holiday' }),
    day(today, 'Unknown', { completed_transaction_count: 1, gross_sales: '75.00' }),
    day(tomorrow, 'PlannedClosed', { closure_reason: 'Planned break' }),
  ])
  expect(await screen.findByRole('button', { name: `${yesterday}: Closed` })).toBeTruthy()
  for (const status of ['Open', 'Closed', 'Unknown', 'PlannedClosed']) {
    expect(document.querySelector(`.calendar-status-${status.toLowerCase()}`)).toBeTruthy()
  }
  selectDate(today)
  const details = screen.getByLabelText(`Details for ${today}`)
  expect(within(details).getByText('₱75.00')).toBeTruthy()
  expect(within(details).getByText('Unknown')).toBeTruthy()
  expect(within(details).getByText('1')).toBeTruthy()
  expect(screen.getByRole('group', { name: 'Operating status legend' })).toBeTruthy()
  expect(within(screen.getByRole('button', { name: `${today}: Unknown` })).getByText('1 completed')).toBeTruthy()
  expect(screen.getByText('Calendar editing is unavailable. This view is read-only.')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Edit date' })).toBeNull()
  expect(screen.queryByRole('checkbox')).toBeNull()
  selectDate(yesterday, 'Closed')
  expect(within(screen.getByLabelText(`Details for ${yesterday}`)).getByText('Holiday')).toBeTruthy()
})

it('shows a past plan as unconfirmed and flags Closed dates with sales', async () => {
  renderCalendar([day(yesterday, 'PlannedClosed', { closure_reason: 'Holiday plan' }),
    day(older, 'Closed', { closure_reason: 'Closure', completed_transaction_count: 1,
      gross_sales: '20.00', inconsistency: true })])
  expect(await screen.findByRole('button', { name: `${yesterday}: Planned closure — outcome unconfirmed` })).toBeTruthy()
  selectDate(older, 'Closed')
  expect(within(screen.getByLabelText(`Details for ${older}`)).getByText(/Closed with completed sales/)).toBeTruthy()
})

it('loads selected-date audit history with prior and current reasons', async () => {
  renderCalendar([day(yesterday, 'Closed', { closure_reason: 'Holiday' })], {
    handler: (url) => url.includes('/history') ? reply(200, [{
      actor_user_id: 4, occurred_at: '2026-11-04T01:00:00+00:00',
      previous_status: 'Unknown', previous_reason: null, previous_version: 0,
      status: 'Closed', closure_reason: 'Holiday', version: 1, bulk: false,
    }]) : undefined,
  })
  await screen.findByRole('button', { name: `${yesterday}: Closed` })
  selectDate(yesterday, 'Closed')
  expect(await screen.findByText(/Unknown → Closed/)).toBeTruthy()
  expect(screen.getByText(/reason: none → Holiday/)).toBeTruthy()
  expect(screen.getByText(/actor #4/)).toBeTruthy()
})

it('preserves versioned correction and CSRF when writes are explicitly enabled for tests', async () => {
  const writes = []
  renderCalendar([day(yesterday, 'Unknown', { version: 2 })], { writesEnabled: true,
    handler: (url, options) => {
      if (options.method === 'PUT') { writes.push({ url, options }); return reply(200, day(yesterday, 'Open')) }
      return undefined
    } })
  await screen.findByRole('button', { name: `${yesterday}: Unknown` })
  selectDate(yesterday)
  fireEvent.click(screen.getByRole('button', { name: 'Edit date' }))
  fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'Open' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save correction' }))
  await waitFor(() => expect(writes).toHaveLength(1))
  expect(writes[0].options.headers['X-CSRF-Token']).toBe('csrf-test')
  expect(JSON.parse(writes[0].options.body)).toEqual({ status: 'Open', closure_reason: null, expected_version: 2 })
})

it('previews historical Unknown dates before bulk Open verification', async () => {
  const writes = []
  renderCalendar([day(older), day(yesterday, 'Unknown', { version: 4 }), day(today)], {
    writesEnabled: true, handler: (url, options) => {
      if (options.method === 'POST') { writes.push(JSON.parse(options.body)); return reply(200, { changed_count: 2, dates: [] }) }
      return undefined
    },
  })
  await screen.findByRole('button', { name: `${older}: Unknown` })
  fireEvent.click(screen.getByLabelText(`Select ${older} for Open verification`))
  fireEvent.click(screen.getByLabelText(`Select ${yesterday} for Open verification`))
  expect(screen.queryByLabelText(`Select ${today} for Open verification`)).toBeNull()
  expect(writes).toHaveLength(0)
  fireEvent.click(screen.getByRole('button', { name: 'Preview selected dates' }))
  expect(screen.getByText('Confirm these 2 dates as verified Open:')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm 2 Open dates' }))
  await waitFor(() => expect(writes).toHaveLength(1))
  expect(writes[0]).toEqual({ dates: [
    { business_date: older, expected_version: 0 }, { business_date: yesterday, expected_version: 4 },
  ] })
})

it.each([
  ['completed_sales_on_date', 'This date has completed sales'],
  ['operating_day_changed', 'This date changed since you reviewed it'],
])('handles %s without overwriting a newer state', async (code, message) => {
  let reads = 0
  renderCalendar([day(yesterday)], { writesEnabled: true, handler: (url, options) => {
    if (options.method === 'PUT') return error(409, code)
    if (!url.includes('/history')) reads += 1
    return undefined
  } })
  await screen.findByRole('button', { name: `${yesterday}: Unknown` })
  selectDate(yesterday)
  fireEvent.click(screen.getByRole('button', { name: 'Edit date' }))
  fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'Open' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save correction' }))
  expect(await screen.findByText(new RegExp(message))).toBeTruthy()
  await waitFor(() => expect(reads).toBe(2))
  expect(screen.queryByRole('form', { name: `Edit ${yesterday}` })).toBeNull()
})

it('becomes read-only if the backend write gate refuses a request', async () => {
  renderCalendar([day(yesterday)], { writesEnabled: true,
    handler: (url, options) => options.method === 'PUT' ? error(404, 'not_found') : undefined })
  await screen.findByRole('button', { name: `${yesterday}: Unknown` })
  selectDate(yesterday)
  fireEvent.click(screen.getByRole('button', { name: 'Edit date' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save correction' }))
  expect(await screen.findByText('Calendar editing is unavailable. This view is read-only.')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Edit date' })).toBeNull()
})

it('shows loading, error, retry, and empty responses', async () => {
  let count = 0
  fetch.mockImplementation(() => Promise.resolve(++count === 1 ? error(500, 'server_error') : reply(200, [])))
  render(<OperatingCalendar onRevalidateSession={revalidate()} />)
  expect(screen.getByText('Loading operating dates…')).toBeTruthy()
  expect(await screen.findByText('The calendar request failed. Please try again.')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByText('No operating dates were returned.')).toBeTruthy()
})

it('keeps Calendar and Weekday views Owner-only in Reports navigation', async () => {
  fetch.mockImplementation(() => Promise.resolve(reply(200, {})))
  const { rerender } = render(<ReportsSection user={{ role: 'Cashier' }} onRevalidateSession={revalidate()} />)
  expect(screen.queryByRole('button', { name: 'Calendar' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Weekday' })).toBeNull()
  rerender(<ReportsSection user={{ role: 'Owner' }} onRevalidateSession={revalidate()} />)
  expect(screen.getByRole('button', { name: 'Calendar' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Weekday' })).toBeTruthy()
})

it('shows Owner editing controls only with the local frontend gate', async () => {
  vi.stubEnv('VITE_CALENDAR_WRITES_ENABLED', '1')
  fetch.mockImplementation((url) => Promise.resolve(url.includes('/operating-days')
    ? reply(200, [day(yesterday)]) : reply(200, {})))
  render(<ReportsSection user={{ role: 'Owner' }} csrfToken="csrf-test"
    onRevalidateSession={revalidate()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Calendar' }))
  await screen.findByRole('button', { name: `${yesterday}: Unknown` })
  selectDate(yesterday)
  expect(screen.getByRole('button', { name: 'Edit date' })).toBeTruthy()
  expect(screen.queryByText('Calendar editing is unavailable. This view is read-only.')).toBeNull()
})
