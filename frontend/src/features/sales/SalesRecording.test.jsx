// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'

import App from '../../app/App.jsx'

const KEY = 'd80be84d-a9d2-46a3-a05e-8a583a04ad0f'
const owner = { user: { id: 1, username: 'synthetic_owner', role: 'Owner' }, csrf_token: 'synthetic-csrf' }
const cashier = { user: { id: 2, username: 'synthetic_cashier', role: 'Cashier' }, csrf_token: 'synthetic-csrf' }
const options = { staff: [{ id: 4, name: 'Ana', role: 'Stylist' }],
  services: [{ id: 5, name: 'Cut', current_price: '101.00', allows_variable_price: false },
    { id: 6, name: 'Color', current_price: '120.00', allows_variable_price: true }],
  products: [{ id: 7, name: 'Oil', current_price: '80.25' }] }
const sale = { id: 11, payment_method: 'Cash', gross_sales: '181.25',
  total_staff_commission: '51.00', total_business_share: '130.25' }
const reply = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body })

function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

function setup(user = cashier, extra = (url) => url === '/api/v1/transactions'
  ? reply(201, sale) : reply(200, { status: 'committed', sale })) {
  fetch.mockImplementation((url) => Promise.resolve(url.endsWith('/me') ? reply(200, user)
    : url.endsWith('/sales/options') ? reply(200, options)
      : url.endsWith('/staff') ? reply(200, []) : extra(url)))
}

async function ready(user = cashier) {
  render(<App />)
  if (user.user.role === 'Owner') {
    await screen.findByRole('button', { name: 'Sales' })
    fireEvent.click(screen.getByRole('button', { name: 'Sales' }))
  }
  await screen.findByRole('heading', { name: 'Sales Recording' })
  await screen.findByText('No items added yet.')
}

function add(name, kind = 'service') {
  if (kind === 'product') fireEvent.click(screen.getByRole('button', { name: 'Products' }))
  if (kind === 'service' && screen.getByRole('button', { name: 'Services' }).getAttribute('aria-pressed') !== 'true') {
    fireEvent.click(screen.getByRole('button', { name: 'Services' }))
  }
  fireEvent.click(screen.getByRole('button', { name: new RegExp(`^Add ${name},`) }))
}

beforeEach(() => {
  window.localStorage.clear()
  window.sessionStorage.clear()
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
  vi.stubGlobal('crypto', { randomUUID: () => KEY })
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('shows Owner Sales section without reauth and keeps management sections', async () => {
  setup(owner)
  render(<App />)
  await screen.findByRole('heading', { name: 'Staff Management' })
  fireEvent.click(screen.getByRole('button', { name: 'Sales' }))
  expect(await screen.findByRole('heading', { name: 'Sales Recording' })).toBeTruthy()
  expect(fetch.mock.calls.filter(([url]) => url.endsWith('/me'))).toHaveLength(1)
  fireEvent.click(screen.getByRole('button', { name: 'Staff' }))
  expect(await screen.findByRole('heading', { name: 'Staff Management' })).toBeTruthy()
})

it('validates Staff, one-unit lines, variable price, and GCash before review', async () => {
  setup()
  await ready()
  add('Cut')
  add('Cut')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  expect(screen.getByText(/Select active Staff/)).toBeTruthy()
  const staff = screen.getAllByLabelText('Staff')
  staff.forEach((field) => fireEvent.change(field, { target: { value: '4' } }))
  expect(screen.getAllByLabelText('Selling price').every((field) => field.disabled)).toBe(true)
  expect(screen.getByLabelText('Payment').value).toBe('Cash')
  expect(screen.queryByText('Payment method')).toBeNull()
  fireEvent.change(screen.getByLabelText('Payment'), { target: { value: 'GCash' } })
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  expect(screen.getByText('Enter the GCash reference.')).toBeTruthy()
  fireEvent.change(screen.getByLabelText('GCash reference'), { target: { value: ' synthetic-ref ' } })
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  const total = screen.getByText('Gross Total')
  expect(total.parentElement.textContent).toBe('Gross Total (provisional)₱202.00')
  expect(screen.getAllByText(/Cut — Ana/)).toHaveLength(2)
  expect(screen.getByText('Payment Method').nextElementSibling.textContent).toBe('GCash')
  expect(screen.getByText('GCash Reference').nextElementSibling.textContent).toBe('synthetic-ref')
  expect(total.parentElement.compareDocumentPosition(screen.getByText('Payment Method')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(screen.queryByText(/Final commissions and Business Share come from the server/)).toBeNull()
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
})

it('submits one line per unit, confirms on lookup, and uses CSRF without browser payload storage', async () => {
  setup()
  await ready()
  add('Cut')
  fireEvent.change(screen.getByLabelText('Staff'), { target: { value: '4' } })
  add('Oil', 'product')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  expect(screen.getByText('Gross Total').parentElement.textContent).toBe('Gross Total (provisional)₱181.25')
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  await screen.findByText('Sale Confirmed')
  const post = fetch.mock.calls.find(([url]) => url === '/api/v1/transactions')
  expect(post[1]).toMatchObject({ method: 'POST', credentials: 'same-origin',
    headers: { 'Idempotency-Key': KEY, 'X-CSRF-Token': 'synthetic-csrf' } })
  expect(JSON.parse(post[1].body)).toEqual({ payment_method: 'Cash', items: [
    { service_id: 5, staff_id: 4, selling_price: '101.00' },
    { product_id: 7, selling_price: '80.25' },
  ] })
  expect(fetch.mock.calls.some(([url]) => url.includes('/by-idempotency-key/'))).toBe(true)
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeNull()
  expect(screen.getByText('Staff Commission').nextElementSibling.textContent).toBe('₱51.00')
  expect(screen.getByText('Gross Sales').nextElementSibling.textContent).toBe('₱181.25')
  expect(screen.getByText('Business Share').nextElementSibling.textContent).toBe('₱130.25')
  expect(screen.getByText('Transaction #11')).toBeTruthy()
  expect(screen.getByText('Payment Method').nextElementSibling.textContent).toBe('Cash')
  expect(screen.getByRole('status').querySelector('.sales-success-icon')).toBeTruthy()
  expect(screen.getByRole('status').querySelector('.sales-summary-gross dd').textContent).toBe('₱181.25')
  expect(screen.queryByRole('heading', { name: 'Items' })).toBeNull()
  expect(screen.queryByRole('heading', { name: 'Payment' })).toBeNull()
  expect(screen.getByRole('button', { name: 'New Sale' })).toBeTruthy()
})

it('preserves exact payload and key on uncertain response and identical 200 retry', async () => {
  let posts = 0
  setup(cashier, (url) => {
    if (url === '/api/v1/transactions') return ++posts === 1 ? Promise.reject(new Error('offline')) : reply(200, sale)
    return reply(200, { status: 'committed', sale })
  })
  await ready()
  add('Color')
  fireEvent.change(screen.getByLabelText('Staff'), { target: { value: '4' } })
  fireEvent.change(screen.getByLabelText('Selling price'), { target: { value: '130.50' } })
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  await screen.findByRole('button', { name: 'Retry exact sale' })
  expect(sessionStorage.getItem('yabs-pending-sale')).toBe(JSON.stringify({ key: KEY, userId: 2 }))
  expect(screen.getByRole('button', { name: 'Confirm sale' }).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Retry exact sale' }))
  await screen.findByText('Sale Confirmed')
  const calls = fetch.mock.calls.filter(([url]) => url === '/api/v1/transactions')
  expect(calls).toHaveLength(2)
  expect(calls[0][1].body).toBe(calls[1][1].body)
  expect(calls[0][1].headers['Idempotency-Key']).toBe(calls[1][1].headers['Idempotency-Key'])
})

it('checks pending after /me on reload and never retries without payload', async () => {
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  setup(cashier, () => reply(202, { status: 'processing', sale: null }))
  render(<App />)
  expect(await screen.findByText(/original sale details are unavailable/i)).toBeTruthy()
  expect(fetch.mock.calls[0][0]).toBe('/api/v1/auth/me')
  expect(fetch.mock.calls.findIndex(([url]) => url.includes('/by-idempotency-key/'))).toBeGreaterThan(0)
  expect(screen.queryByRole('button', { name: 'Retry exact sale' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Review sale' }).disabled).toBe(true)
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeTruthy()
})

it('keeps not_committed_at_check unresolved and does not lookup another user key', async () => {
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  setup(cashier, () => reply(200, { status: 'not_committed_at_check', sale: null }))
  render(<App />)
  expect(await screen.findByText(/earlier request may still complete/i)).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Review sale' }).disabled).toBe(true)
  cleanup()
  fetch.mockClear()
  setup(owner)
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'Sales' }))
  expect(await screen.findByText(/unresolved sale for another account/i)).toBeTruthy()
  expect(fetch.mock.calls.some(([url]) => url.includes('/by-idempotency-key/'))).toBe(false)
})

it('fails closed before POST when sessionStorage cannot persist a key', async () => {
  setup()
  await ready()
  add('Oil', 'product')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  expect(await screen.findByText(/pending sale state cannot be safely read or saved/i)).toBeTruthy()
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
})

it('prevents duplicate submission while a POST remains in flight', async () => {
  const pending = deferred()
  setup(cashier, (url) => url === '/api/v1/transactions' ? pending.promise : reply(202, { status: 'processing', sale: null }))
  await ready()
  add('Oil', 'product')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  expect(screen.getByRole('button', { name: 'Confirm sale' }).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/transactions')).toHaveLength(1)
  pending.resolve(reply(201, sale))
  await screen.findByText(/Sale is still processing/i)
})

it('restores a committed pending sale after /me without another POST', async () => {
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  setup()
  render(<App />)
  expect(await screen.findByText('Sale Confirmed')).toBeTruthy()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeNull()
  expect(fetch.mock.calls[0][0]).toBe('/api/v1/auth/me')
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
})

it('keeps an unresolved payload across Owner section switches', async () => {
  setup(owner, (url) => url === '/api/v1/transactions'
    ? Promise.reject(new Error('offline')) : reply(200, { status: 'not_committed_at_check', sale: null }))
  await ready(owner)
  add('Oil', 'product')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  await screen.findByRole('button', { name: 'Retry exact sale' })
  fireEvent.click(screen.getByRole('button', { name: 'Staff' }))
  await screen.findByRole('heading', { name: 'Staff Management' })
  fireEvent.click(screen.getByRole('button', { name: 'Sales' }))
  expect(await screen.findByRole('button', { name: 'Retry exact sale' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Review sale' }).disabled).toBe(true)
})

it.each([401, 403, 409, 422])('keeps pending after POST %i without claiming success', async (status) => {
  fetch.mockImplementation((url) => Promise.resolve(url.endsWith('/me') ? reply(200, cashier)
    : url.endsWith('/sales/options') ? reply(200, options)
      : url === '/api/v1/transactions' ? reply(status, { error: { code: 'synthetic' } })
        : reply(200, { status: 'not_committed_at_check', sale: null })))
  await ready()
  add('Oil', 'product')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  expect(await screen.findByRole('button', { name: 'Retry exact sale' })).toBeTruthy()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeTruthy()
  expect(screen.queryByText('Sale Confirmed')).toBeNull()
  if (status === 401) expect(fetch.mock.calls.filter(([url]) => url.endsWith('/me'))).toHaveLength(2)
})

it('shows a retryable options error and does not submit when options fail', async () => {
  fetch.mockImplementation((url) => Promise.resolve(url.endsWith('/me') ? reply(200, cashier)
    : reply(403, { error: { code: 'forbidden' } })))
  render(<App />)
  expect(await screen.findByText('You do not have permission to record sales.')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy()
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
})

it('shows a compact GCash confirmation and starts a fresh form without reusing the key', async () => {
  const gcashSale = { ...sale, payment_method: 'GCash', gross_sales: '1234.50',
    total_staff_commission: '70.00', total_business_share: '1164.50' }
  setup(cashier, (url) => url === '/api/v1/transactions' ? reply(201, gcashSale)
    : reply(200, { status: 'committed', sale: gcashSale }))
  const uuid = vi.spyOn(crypto, 'randomUUID')
  await ready()
  add('Oil', 'product')
  fireEvent.change(screen.getByLabelText('Payment'), { target: { value: 'GCash' } })
  fireEvent.change(screen.getByLabelText('GCash reference'), { target: { value: 'synthetic-ref' } })
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  await screen.findByRole('heading', { name: 'Sale Confirmed' })
  expect(screen.getByText('Payment Method').nextElementSibling.textContent).toBe('GCash')
  expect(screen.getByText('Gross Sales').nextElementSibling.textContent).toBe('₱1,234.50')
  expect(screen.queryByRole('heading', { name: 'Items' })).toBeNull()
  expect(screen.queryByRole('heading', { name: 'Payment' })).toBeNull()
  expect(uuid).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button', { name: 'New Sale' }))
  expect(await screen.findByRole('heading', { name: 'Sales Recording' })).toBeTruthy()
  expect(screen.getByText('No items added yet.')).toBeTruthy()
  expect(screen.getByLabelText('Payment').value).toBe('Cash')
  expect(screen.queryByLabelText('GCash reference')).toBeNull()
  expect(screen.queryByRole('button', { name: 'New Sale' })).toBeNull()
  expect(uuid).toHaveBeenCalledTimes(1)
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/transactions')).toHaveLength(1)
})

it('never offers New Sale while committed lookup cannot clear the pending key', async () => {
  setup()
  await ready()
  add('Oil', 'product')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('blocked') })
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  expect(await screen.findByText(/pending browser state could not be cleared/i)).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'New Sale' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Confirm sale' }).disabled).toBe(true)
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeTruthy()
})

it('blocks New Sale if a pending identifier reappears after confirmation', async () => {
  setup()
  await ready()
  add('Oil', 'product')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  await screen.findByRole('heading', { name: 'Sale Confirmed' })
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  fireEvent.click(screen.getByRole('button', { name: 'New Sale' }))
  expect(screen.getByRole('heading', { name: 'Sale Confirmed' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'New Sale' }).disabled).toBe(true)
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/transactions')).toHaveLength(1)
})

it('searches active catalog rows and preserves sale lines across item tabs', async () => {
  setup()
  await ready()
  const search = screen.getByRole('searchbox', { name: 'Name' })
  expect(search.getAttribute('placeholder')).toBe('Search')
  expect(search.parentElement.querySelector('svg[aria-hidden="true"]')).toBeTruthy()
  fireEvent.change(search, { target: { value: 'cUt' } })
  expect(screen.getByRole('button', { name: 'Add Cut, ₱101.00' })).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Add Color, ₱120.00' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Add Cut, ₱101.00' }))
  fireEvent.click(screen.getByRole('button', { name: 'Products' }))
  expect(screen.getByRole('button', { name: 'Products' }).getAttribute('aria-pressed')).toBe('true')
  expect(screen.getByText('1. Cut')).toBeTruthy()
  expect(search.value).toBe('')
  fireEvent.change(search, { target: { value: 'nothing' } })
  expect(screen.getByText('No items match your search.')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Add Oil, ₱80.25' })).toBeNull()
  fireEvent.change(search, { target: { value: '' } })
  expect(screen.getByRole('button', { name: 'Add Oil, ₱80.25' })).toBeTruthy()
  expect(fetch.mock.calls.filter(([url]) => url.endsWith('/sales/options'))).toHaveLength(1)
})

it('adds repeated clicks as separate units and updates the provisional total on removal', async () => {
  setup()
  await ready()
  const cut = screen.getByRole('button', { name: 'Add Cut, ₱101.00' })
  fireEvent.click(cut)
  fireEvent.click(cut)
  expect(screen.getByText('1. Cut')).toBeTruthy()
  expect(screen.getByText('2. Cut')).toBeTruthy()
  expect(screen.getAllByLabelText('Staff')).toHaveLength(2)
  expect(screen.getByText('₱202.00')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Remove Cut line 1' }))
  expect(screen.getAllByLabelText('Staff')).toHaveLength(1)
  expect(within(screen.getByRole('region', { name: 'Current Sale' })).getByText('₱101.00')).toBeTruthy()
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
})

it('hides the numeric provisional total when a variable price is invalid', async () => {
  setup()
  await ready()
  add('Color')
  const price = screen.getByLabelText('Selling price')
  expect(price.disabled).toBe(false)
  expect(within(screen.getByRole('region', { name: 'Current Sale' })).getByText('₱120.00')).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Staff'), { target: { value: '4' } })
  fireEvent.change(price, { target: { value: '0.00' } })
  expect(screen.getByText('Enter valid selling prices')).toBeTruthy()
  expect(screen.queryByText('₱0.00')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  expect(screen.getByText(/Check selling prices/)).toBeTruthy()
  fireEvent.change(price, { target: { value: '130.50' } })
  expect(screen.getByText('₱130.50')).toBeTruthy()
  add('Oil', 'product')
  expect(screen.getAllByLabelText('Selling price')[1].disabled).toBe(true)
})

it('formats a large provisional receipt total without submitting a sale', async () => {
  setup()
  await ready()
  add('Color')
  fireEvent.change(screen.getByLabelText('Staff'), { target: { value: '4' } })
  fireEvent.change(screen.getByLabelText('Selling price'), { target: { value: '2222.00' } })
  add('Oil', 'product')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  expect(screen.getByText('Gross Total').parentElement.textContent).toBe('Gross Total (provisional)₱2,302.25')
  expect(screen.getByText('Payment Method').nextElementSibling.textContent).toBe('Cash')
  expect(screen.queryByText('GCash Reference')).toBeNull()
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
})

it('replaces editable Current Sale with review and restores it on Back', async () => {
  setup()
  await ready()
  add('Cut')
  fireEvent.change(screen.getByLabelText('Staff'), { target: { value: '4' } })
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  expect(screen.getByRole('heading', { name: 'Review sale' })).toBeTruthy()
  expect(screen.queryByLabelText('Staff')).toBeNull()
  expect(screen.queryByLabelText('Payment')).toBeNull()
  expect(screen.getByRole('button', { name: 'Add Cut, ₱101.00' }).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Back' }))
  expect(screen.getByRole('heading', { name: 'Current Sale' })).toBeTruthy()
  expect(screen.getByLabelText('Staff').value).toBe('4')
  expect(screen.getByRole('button', { name: 'Add Cut, ₱101.00' }).disabled).toBe(false)
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
})

it('shows long catalog names and a clear empty catalog state without clipping the data', async () => {
  const longName = 'Detailed Salon Treatment With A Very Long Descriptive Name'
  fetch.mockImplementation((url) => Promise.resolve(url.endsWith('/me') ? reply(200, cashier)
    : reply(200, { staff: options.staff, services: [{ id: 9, name: longName, current_price: '200.00', allows_variable_price: false }], products: [] })))
  await ready()
  expect(screen.getByRole('button', { name: `Add ${longName}, ₱200.00` })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: `Add ${longName}, ₱200.00` }))
  expect(screen.getByText(`1. ${longName}`)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Products' }))
  expect(screen.getByText('No active products are available.')).toBeTruthy()
})
