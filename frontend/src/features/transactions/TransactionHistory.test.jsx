// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'

import TransactionHistory from './TransactionHistory.jsx'

const owner = { id: 1, username: 'synthetic_owner', role: 'Owner' }
const cashier = { id: 2, username: 'synthetic_cashier', role: 'Cashier' }
const row = { id: 7, daily_number: 1, date_time: '2026-10-23T02:30:00+00:00', business_date: '2026-10-23',
  status: 'Completed', payment_method: 'GCash', gross_sales: '101.00',
  total_staff_commission: '51.00', total_business_share: '50.00' }
const item = { id: 10, item_name_snapshot: 'Original Haircut', selling_price: '101.00',
  staff_id: 4, staff_name: 'Ana', service_id: 3, product_id: null,
  commission_type_snapshot: 'Percentage', commission_value_snapshot: '50.00',
  staff_commission: '51.00', business_share: '50.00' }
const detail = { ...row, gcash_reference: 'synthetic-gcash-ref', items: [item],
  created_at: '2026-10-23T02:30:00+00:00', recorded_by_user_id: 1, entry_source: 'Direct',
  manual_reference: null, void_reason: null, voided_by_user_id: null, voided_at: null }
const reply = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
const page = (items = [row], next_cursor = null) => ({ items, next_cursor })
const deferred = () => {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

function setup(user = owner, handler = (url) => url.includes('?')
  ? reply(200, page()) : reply(200, detail)) {
  fetch.mockImplementation((url, options) => Promise.resolve(handler(url, options)))
  const onRevalidateSession = vi.fn().mockResolvedValue(true)
  render(<TransactionHistory user={user} csrfToken="synthetic-csrf"
    onRevalidateSession={onRevalidateSession} />)
  return onRevalidateSession
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
  HTMLDialogElement.prototype.showModal = function () { this.open = true }
  HTMLDialogElement.prototype.close = function () { this.open = false }
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('shows Owner financial history, Voided status, and a server-side business-date filter', async () => {
  setup(owner, (url) => reply(200, page([{ ...row, status: 'Voided' }])))
  const table = await screen.findByRole('table')
  expect(within(table).getByText('₱101.00')).toBeTruthy()
  expect(within(table).getByText('₱51.00')).toBeTruthy()
  expect(within(table).getByText('₱50.00')).toBeTruthy()
  expect(within(table).getByText('Voided')).toBeTruthy()
  expect(within(table).getByText('#7')).toBeTruthy()
  expect(within(table).getByText('Action')).toBeTruthy()
  expect(within(table).getByText(/Oct 23, 2026/)).toBeTruthy()
  expect(screen.getByLabelText('Business date')).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Business date'), { target: { value: '2026-10-20' } })
  await waitFor(() => expect(fetch.mock.calls.at(-1)[0]).toContain('business_date=2026-10-20'))
  expect(screen.getByText('Page 1')).toBeTruthy()
})

it('limits Cashier UI to today and shows authorized financial snapshots and GCash detail', async () => {
  setup(cashier, (url) => url.includes('?') ? reply(200, page())
    : reply(200, (({ void_reason, voided_at, voided_by_user_id, ...safe }) => safe)(detail)))
  const table = await screen.findByRole('table')
  expect(screen.queryByLabelText('Business date')).toBeNull()
  expect(fetch.mock.calls[0][0]).not.toContain('business_date=')
  expect(within(table).getByText('₱51.00')).toBeTruthy()
  expect(within(table).getByText('₱50.00')).toBeTruthy()
  expect(screen.queryByText('synthetic-gcash-ref')).toBeNull()
  expect(within(table).getByText('#1')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'View transaction #1' }))
  expect(await screen.findByRole('heading', { name: 'Transaction #1' })).toBeTruthy()
  expect(fetch.mock.calls.at(-1)[0]).toBe('/api/v1/transactions/7')
  expect(screen.getByText('Original Haircut')).toBeTruthy()
  expect(screen.getByText('Staff: Ana')).toBeTruthy()
  expect(screen.getByText('Commission at sale')).toBeTruthy()
  expect(within(table).queryByText('Action')).toBeNull()
  expect(screen.getByText('Percentage · 50.00%')).toBeTruthy()
  expect(screen.getByText('synthetic-gcash-ref')).toBeTruthy()
  expect(screen.queryByText('Entry source')).toBeNull()
  expect(screen.queryByText('Paper reference')).toBeNull()
  expect(screen.queryByText('Void reason')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Void transaction' })).toBeNull()
})

it('shows server daily numbers across Cashier pages while opening details by database ID', async () => {
  setup(cashier, (url) => url.includes('cursor=next')
    ? reply(200, page([{ ...row, id: 9, daily_number: 2 }]))
    : url.includes('?') ? reply(200, page([row], 'next'))
      : reply(200, { ...detail, id: 9, daily_number: 2 }))
  expect(await screen.findByRole('button', { name: 'View transaction #1' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  expect(await screen.findByRole('button', { name: 'View transaction #2' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'View transaction #2' }))
  expect(await screen.findByRole('heading', { name: 'Transaction #2' })).toBeTruthy()
  expect(fetch.mock.calls.at(-1)[0]).toBe('/api/v1/transactions/9')
})

it('shows Manual paper provenance and entry time to Owner only', async () => {
  const manual = { ...detail, entry_source: 'Manual', manual_reference: 'PAPER-20261023-001',
    created_at: '2026-10-24T02:30:00+00:00' }
  setup(owner, (url) => url.includes('?') ? reply(200, page()) : reply(200, manual))
  await screen.findByRole('table')
  fireEvent.click(screen.getByRole('button', { name: 'View transaction #7' }))
  await screen.findByRole('heading', { name: 'Transaction #7' })
  expect(screen.getByText('Entry source').nextElementSibling.textContent).toBe('Manual')
  expect(screen.getByText('Paper reference').nextElementSibling.textContent).toBe('PAPER-20261023-001')
  expect(screen.getByText('Entry time').nextElementSibling.textContent).toMatch(/Oct 24, 2026/)
})

it('uses bounded cursors, supports Back, and resets the page on a date change', async () => {
  setup(owner, (url) => url.includes('cursor=opaque-next') ? reply(200, page([row]))
    : url.includes('business_date=2026-10-20') ? reply(200, page([]))
      : reply(200, page([{ ...row, id: 6 }], 'opaque-next')))
  await screen.findByRole('button', { name: 'View transaction #6' })
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  expect(await screen.findByRole('button', { name: 'View transaction #7' })).toBeTruthy()
  expect(screen.getByText('Page 2')).toBeTruthy()
  expect(fetch.mock.calls.at(-1)[0]).toContain('cursor=opaque-next')
  fireEvent.click(screen.getByRole('button', { name: 'Back' }))
  expect(await screen.findByRole('button', { name: 'View transaction #6' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  await screen.findByRole('button', { name: 'View transaction #7' })
  fireEvent.change(screen.getByLabelText('Business date'), { target: { value: '2026-10-20' } })
  expect(await screen.findByText('No transactions for this business date.')).toBeTruthy()
  expect(screen.getByText('Page 1')).toBeTruthy()
  expect(fetch.mock.calls.at(-1)[0]).not.toContain('cursor=')
})

it('displays the backend ascending order without reversing the list', async () => {
  setup(owner, () => reply(200, page([1, 2, 3, 4, 5, 6].map((id) => ({ ...row, id })))))
  await screen.findByRole('table')
  expect(screen.getAllByRole('button', { name: /^View transaction #/ })
    .map((button) => button.getAttribute('aria-label'))).toEqual(
    [1, 2, 3, 4, 5, 6].map((id) => `View transaction #${id}`))
})

it('returns to page one when an old cursor is rejected after a backend deployment', async () => {
  setup(owner, (url) => url.includes('cursor=old-order-cursor') ? reply(422, {})
    : reply(200, page([{ ...row, id: 6 }], 'old-order-cursor')))
  await screen.findByRole('button', { name: 'View transaction #6' })
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  expect(await screen.findByText('History pagination changed. Showing the first page again.')).toBeTruthy()
  expect(await screen.findByText('Page 1')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'View transaction #6' })).toBeTruthy()
  expect(fetch.mock.calls.filter(([url]) => url.includes('cursor=old-order-cursor'))).toHaveLength(1)
})

it('ignores old date and detail responses after the user changes selection', async () => {
  const oldPage = deferred()
  const oldDetail = deferred()
  setup(owner, (url) => url.includes('business_date=2026-10-20') ? oldPage.promise
    : url.includes('business_date=2026-10-21') ? reply(200, page([{ ...row, id: 8 }]))
      : url.endsWith('/7') ? oldDetail.promise : reply(200, page()))
  await screen.findByRole('button', { name: 'View transaction #7' })
  fireEvent.click(screen.getByRole('button', { name: 'View transaction #7' }))
  await waitFor(() => expect(fetch.mock.calls.some(([url]) => url.endsWith('/7'))).toBe(true))
  fireEvent.click(screen.getByRole('button', { name: 'Back to history' }))
  fireEvent.change(screen.getByLabelText('Business date'), { target: { value: '2026-10-20' } })
  await waitFor(() => expect(fetch.mock.calls.at(-1)[0]).toContain('2026-10-20'))
  fireEvent.change(screen.getByLabelText('Business date'), { target: { value: '2026-10-21' } })
  expect(await screen.findByRole('button', { name: 'View transaction #8' })).toBeTruthy()
  oldPage.resolve(reply(200, page([{ ...row, id: 99 }])))
  oldDetail.resolve(reply(200, detail))
  await waitFor(() => expect(screen.queryByRole('button', { name: 'View transaction #99' })).toBeNull())
  expect(screen.queryByRole('heading', { name: 'Transaction #7' })).toBeNull()
})

it('confirms Owner void with CSRF, validates the reason, and waits for the server result', async () => {
  const post = deferred()
  setup(owner, (url) => url.includes('?') ? reply(200, page())
    : url.endsWith('/void') ? post.promise : reply(200, detail))
  fireEvent.click(await screen.findByRole('button', { name: 'View transaction #7' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Void transaction' }))
  expect(document.querySelector('dialog').open).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Confirm void' }))
  expect(screen.getByText('Enter a nonblank reason of at most 500 characters.')).toBeTruthy()
  expect(fetch.mock.calls.filter(([url]) => url.endsWith('/void'))).toHaveLength(0)
  fireEvent.change(screen.getByLabelText('Reason'), { target: { value: '  Mistaken sale  ' } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirm void' }))
  expect(screen.getByText('Completed')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Voiding…' }).disabled).toBe(true)
  expect(screen.getByRole('button', { name: 'Back to history' }).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Voiding…' }))
  expect(fetch.mock.calls.filter(([url]) => url.endsWith('/void'))).toHaveLength(1)
  const [, options] = fetch.mock.calls.find(([url]) => url.endsWith('/void'))
  expect(options.credentials).toBe('same-origin')
  expect(options.headers['X-CSRF-Token']).toBe('synthetic-csrf')
  expect(JSON.parse(options.body)).toEqual({ reason: 'Mistaken sale' })
  post.resolve(reply(200, { ...detail, status: 'Voided', void_reason: 'Mistaken sale',
    voided_by_user_id: 1, voided_at: '2026-10-23T03:00:00+00:00' }))
  expect(await screen.findByText('Mistaken sale')).toBeTruthy()
  expect(screen.getByText('Voided')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Void transaction' })).toBeNull()
})

it('lets Owner cancel without sending a void and keeps Cashier unable to submit one', async () => {
  setup()
  fireEvent.click(await screen.findByRole('button', { name: 'View transaction #7' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Void transaction' }))
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(document.querySelector('dialog').open).toBe(false)
  expect(fetch.mock.calls.some(([url]) => url.endsWith('/void'))).toBe(false)
})

it('renders Owner-only void metadata without changing stored financial snapshots', async () => {
  setup(owner, (url) => url.includes('?') ? reply(200, page([{ ...row, status: 'Voided' }]))
    : reply(200, { ...detail, status: 'Voided', void_reason: 'Duplicate paper entry',
      voided_by_user_id: 1, voided_at: row.date_time }))
  fireEvent.click(await screen.findByRole('button', { name: 'View transaction #7' }))
  expect(await screen.findByText('Duplicate paper entry')).toBeTruthy()
  expect(screen.getAllByText('₱101.00')).toHaveLength(2)
  expect(screen.getAllByText('₱51.00').length).toBeGreaterThan(0)
  expect(screen.getByText('User #1')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Void transaction' })).toBeNull()
})

it.each([403, 404, 422, 500])('shows a retryable list error for HTTP %i', async (status) => {
  setup(cashier, () => reply(status, { error: { code: 'synthetic' } }))
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy()
  expect(screen.queryByRole('table')).toBeNull()
})

it('does not display a Cashier detail when the server denies access', async () => {
  setup(cashier, (url) => url.includes('?') ? reply(200, page()) : reply(404, {}))
  fireEvent.click(await screen.findByRole('button', { name: 'View transaction #1' }))
  expect(await screen.findByText('Transaction not found or no longer available to you.')).toBeTruthy()
  expect(screen.queryByText('Original Haircut')).toBeNull()
  expect(screen.queryByText('synthetic-gcash-ref')).toBeNull()
})

it('offers retry after a network failure without showing stale history', async () => {
  fetch.mockRejectedValue(new Error('synthetic network error'))
  render(<TransactionHistory user={cashier} csrfToken="synthetic-csrf"
    onRevalidateSession={vi.fn()} />)
  expect(await screen.findByText('Transaction History is temporarily unavailable. Please try again.')).toBeTruthy()
  expect(screen.queryByRole('table')).toBeNull()
  expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy()
})

it('revalidates an expired session and does not expose history data', async () => {
  const onRevalidateSession = setup(cashier, () => reply(401, {}))
  await waitFor(() => expect(onRevalidateSession).toHaveBeenCalledTimes(1))
  expect(screen.queryByRole('table')).toBeNull()
})

it('refetches after a void conflict or ambiguous failure without claiming success', async () => {
  let detailReads = 0
  setup(owner, (url) => url.includes('?') ? reply(200, page())
    : url.endsWith('/void') ? reply(409, {})
      : reply(200, ++detailReads === 1 ? detail : { ...detail, status: 'Voided',
        void_reason: 'Earlier void', voided_by_user_id: 1, voided_at: row.date_time }))
  fireEvent.click(await screen.findByRole('button', { name: 'View transaction #7' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Void transaction' }))
  fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Mistake' } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirm void' }))
  expect(await screen.findByText('Earlier void')).toBeTruthy()
  expect(detailReads).toBe(2)
  expect(screen.queryByRole('button', { name: 'Void transaction' })).toBeNull()
})

it('keeps an ambiguous void outcome unresolved and refetches detail', async () => {
  let detailReads = 0
  fetch.mockImplementation((url) => url.includes('?') ? Promise.resolve(reply(200, page()))
    : url.endsWith('/void') ? Promise.reject(new Error('synthetic disconnect'))
      : Promise.resolve(reply(200, ++detailReads === 1 ? detail : { ...detail })))
  render(<TransactionHistory user={owner} csrfToken="synthetic-csrf"
    onRevalidateSession={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: 'View transaction #7' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Void transaction' }))
  fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Mistake' } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirm void' }))
  expect(await screen.findByText(/Void outcome could not be confirmed/)).toBeTruthy()
  await waitFor(() => expect(detailReads).toBe(2))
  expect(screen.queryByRole('button', { name: 'Void transaction' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Check status again' })).toBeTruthy()
  expect(fetch.mock.calls.filter(([url]) => url.endsWith('/void'))).toHaveLength(1)
})

it('refreshes Cashier history after the Manila business date changes', async () => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-22T15:59:00Z'))
  setup(cashier)
  await screen.findByRole('table')
  const before = fetch.mock.calls.length
  vi.setSystemTime(new Date('2026-10-22T16:00:00Z'))
  fireEvent(window, new Event('focus'))
  await waitFor(() => expect(fetch.mock.calls.length).toBe(before + 1))
  expect(screen.getByText(/Manila business date changed/)).toBeTruthy()
})
