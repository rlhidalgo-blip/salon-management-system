// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'

import App from '../../app/App.jsx'
import OwnerSaleReconciliation from './OwnerSaleReconciliation.jsx'

const KEY = 'd80be84d-a9d2-46a3-a05e-8a583a04ad0f'
const owner = { user: { id: 1, username: 'synthetic_owner', role: 'Owner' }, csrf_token: 'synthetic-csrf' }
const cashier = { user: { id: 2, username: 'synthetic_cashier', role: 'Cashier' }, csrf_token: 'synthetic-csrf' }
const options = { staff: [{ id: 4, name: 'Ana', role: 'Stylist' }],
  services: [{ id: 5, name: 'Cut', current_price: '101.00', allows_variable_price: false },
    { id: 6, name: 'Color', current_price: '120.00', allows_variable_price: true }],
  products: [{ id: 7, name: 'Oil', current_price: '80.25' }] }
const manualOptions = { staff: [{ id: 4, name: 'Ana', role: 'Stylist', active: false }],
  services: [{ id: 5, name: 'Cut', active: false }], products: [{ id: 7, name: 'Oil', active: true }] }
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

function reservedSetup(user = cashier, extra = () => null, open = null) {
  fetch.rawImplementation((url, init) => {
    if (url.endsWith('/me')) return Promise.resolve(reply(200, user))
    if (url === '/api/v1/sales/capabilities') return Promise.resolve(reply(200, { protocol: 'reserved_v1' }))
    if (url === '/api/v1/sales/attempts/open') return Promise.resolve(reply(200, open))
    if (url === '/api/v1/sales/options') return Promise.resolve(reply(200, options))
    if (url === '/api/v1/sales/manual-options') return Promise.resolve(reply(200, manualOptions))
    if (url === '/api/v1/staff') return Promise.resolve(reply(200, []))
    return extra(url, init) ?? Promise.resolve(reply(200, { status: 'committed', sale }))
  })
}

function reservedReply(source, paperReference, userId = 2) {
  return { id: 12, user_id: userId, idempotency_key: KEY, source, state: 'Reserved',
    direct_reference: source === 'Direct' ? 'DS-000000000012' : null,
    manual_reference: source === 'Manual' ? paperReference : null }
}

function investigationRow(id, state = 'Reserved', source = 'Direct') {
  return { id, user_id: 2, idempotency_key: KEY, source, state,
    direct_reference: source === 'Direct' ? `DS-${String(id).padStart(12, '0')}` : null,
    manual_reference: source === 'Manual' ? 'PAPER-20261027-001' : null,
    created_at: '2026-10-27T08:00:00+08:00' }
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

function currentSaleNames() {
  return [...screen.getByRole('region', { name: 'Current Sale' }).querySelectorAll('.sales-line-name')]
    .map((name) => name.textContent)
}

function manilaMinute() {
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit',
    day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
    .format(new Date(Date.now() - 60_000)).replace(' ', 'T')
}

async function manualReady() {
  fireEvent.click(screen.getByRole('button', { name: 'Manual Entry' }))
  await screen.findByRole('button', { name: 'Add Cut, Inactive now' })
}

function fillManualService() {
  const occurrence = manilaMinute()
  fireEvent.change(screen.getByLabelText('Original date & time (Manila)'), { target: { value: occurrence } })
  fireEvent.change(screen.getByLabelText('Paper reference'), { target: {
    value: ` paper-${occurrence.slice(0, 10).replaceAll('-', '')}-001 `,
  } })
  fireEvent.click(screen.getByRole('button', { name: 'Add Cut, Inactive now' }))
  fireEvent.change(screen.getByLabelText('Staff'), { target: { value: '4' } })
  fireEvent.change(screen.getByLabelText('Name on paper'), { target: { value: 'Old Cut' } })
  fireEvent.change(screen.getByLabelText('Price on paper'), { target: { value: '101.00' } })
  fireEvent.change(screen.getByLabelText('Commission rate (%)'), { target: { value: '50.00' } })
  fireEvent.click(screen.getByLabelText(/I verified the original paper record/i))
}

beforeEach(() => {
  window.localStorage.clear()
  window.sessionStorage.clear()
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
  vi.stubGlobal('crypto', { randomUUID: () => KEY })
  const mockedFetch = vi.fn()
  const rawImplementation = mockedFetch.mockImplementation.bind(mockedFetch)
  // Existing regression cases run against the explicit default-off server mode.
  mockedFetch.mockImplementation = (handler) => rawImplementation((url, options) =>
    url === '/api/v1/sales/capabilities' ? Promise.resolve(reply(200, { protocol: 'legacy' }))
      : handler(url, options))
  mockedFetch.rawImplementation = rawImplementation
  vi.stubGlobal('fetch', mockedFetch)
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it.each([404, 500])('blocks electronic sales when capability check returns %i', async (code) => {
  fetch.rawImplementation((url) => Promise.resolve(url.endsWith('/me') ? reply(200, cashier)
    : url === '/api/v1/sales/capabilities' ? reply(code, {})
      : url === '/api/v1/sales/options' ? reply(200, options) : reply(404, {})))
  await ready()
  await screen.findByText(/Sales protocol could not be verified/i)
  expect(screen.getByRole('button', { name: 'Review sale' }).disabled).toBe(true)
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
})

it('rejects an invalid capability body without treating it as legacy', async () => {
  fetch.rawImplementation((url) => Promise.resolve(url.endsWith('/me') ? reply(200, cashier)
    : url === '/api/v1/sales/capabilities' ? reply(200, { protocol: 'unknown' })
      : url === '/api/v1/sales/options' ? reply(200, options) : reply(404, {})))
  await ready()
  await screen.findByText(/Sales protocol could not be verified/i)
  expect(screen.getByRole('button', { name: 'Review sale' }).disabled).toBe(true)
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
})

it('blocks a protocol change before allocating a UUID or posting either sale type', async () => {
  let checks = 0
  fetch.rawImplementation((url) => Promise.resolve(url.endsWith('/me') ? reply(200, cashier)
    : url === '/api/v1/sales/capabilities' ? reply(200, { protocol: ++checks === 1 ? 'legacy' : 'reserved_v1' })
      : url === '/api/v1/sales/options' ? reply(200, options) : reply(404, {})))
  const uuid = vi.spyOn(crypto, 'randomUUID')
  await ready()
  add('Oil', 'product')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  await screen.findByText(/Sales protocol or browser storage could not be verified/i)
  expect(uuid).not.toHaveBeenCalled()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeNull()
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions' ||
    url === '/api/v1/sales/attempts')).toBe(false)
})

it('reserves Direct payload and key before POST, then requires physical-reference acknowledgment', async () => {
  reservedSetup(cashier, (url, init) => {
    if (url === '/api/v1/sales/attempts') return Promise.resolve(reply(201, reservedReply('Direct')))
    if (url === '/api/v1/transactions') return Promise.resolve(reply(201, sale))
    return null
  })
  await ready()
  add('Oil', 'product')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  expect(await screen.findByText(/Direct reference: DS-000000000012/)).toBeTruthy()
  const reservation = fetch.mock.calls.find(([url]) => url === '/api/v1/sales/attempts')
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/sales/capabilities')).toHaveLength(2)
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/sales/attempts/open')).toHaveLength(2)
  expect(reservation[1].headers['Idempotency-Key']).toBe(KEY)
  expect(reservation[1].headers['X-CSRF-Token']).toBe('synthetic-csrf')
  expect(reservation[1].credentials).toBe('same-origin')
  expect(JSON.parse(reservation[1].body)).toEqual({ source: 'Direct', sale: {
    payment_method: 'Cash', items: [{ product_id: 7, selling_price: '80.25' }],
  } })
  expect(sessionStorage.getItem('yabs-pending-sale')).toBe(JSON.stringify({ key: KEY, userId: 2 }))
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
  const send = screen.getByRole('button', { name: 'Submit reserved sale' })
  expect(send.disabled).toBe(true)
  fireEvent.click(screen.getByLabelText(/I recorded this Direct reference/i))
  fireEvent.click(send)
  await screen.findByRole('heading', { name: 'Sale Confirmed' })
  const post = fetch.mock.calls.find(([url]) => url === '/api/v1/transactions')
  expect(post[1].body).toBe(JSON.stringify(JSON.parse(reservation[1].body).sale))
  expect(post[1].headers['Idempotency-Key']).toBe(KEY)
  expect(fetch.mock.calls.indexOf(reservation)).toBeLessThan(fetch.mock.calls.indexOf(post))
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeNull()
})

it('reserves normalized Manual reference before submitting the exact original payload', async () => {
  reservedSetup(cashier, (url, init) => {
    if (url === '/api/v1/sales/attempts') return Promise.resolve(reply(201,
      reservedReply('Manual', JSON.parse(init.body).sale.manual_reference)))
    if (url === '/api/v1/transactions/manual') return Promise.resolve(reply(201, sale))
    return null
  })
  await ready()
  await manualReady()
  fillManualService()
  fireEvent.click(screen.getByRole('button', { name: 'Review Manual sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm Manual sale' }))
  await screen.findByRole('heading', { name: 'Sale Confirmed' })
  const reservation = fetch.mock.calls.find(([url]) => url === '/api/v1/sales/attempts')
  const post = fetch.mock.calls.find(([url]) => url === '/api/v1/transactions/manual')
  expect(JSON.parse(reservation[1].body).source).toBe('Manual')
  expect(JSON.parse(reservation[1].body).sale.manual_reference).toMatch(/^PAPER-\d{8}-001$/)
  expect(post[1].body).toBe(JSON.stringify(JSON.parse(reservation[1].body).sale))
  expect(reservation[1].headers['Idempotency-Key']).toBe(post[1].headers['Idempotency-Key'])
  expect(fetch.mock.calls.indexOf(reservation)).toBeLessThan(fetch.mock.calls.indexOf(post))
})

it('keeps the UUID after lost reservation response and retries that exact reservation', async () => {
  let requests = 0
  reservedSetup(cashier, (url) => {
    if (url === '/api/v1/sales/attempts') {
      requests += 1
      return requests === 1 ? Promise.reject(new Error('network'))
        : Promise.resolve(reply(200, reservedReply('Direct')))
    }
    return null
  })
  await ready()
  add('Oil', 'product')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  await screen.findByText(/Reservation outcome is uncertain/i)
  expect(sessionStorage.getItem('yabs-pending-sale')).toBe(JSON.stringify({ key: KEY, userId: 2 }))
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Retry exact sale' }))
  expect(await screen.findByText(/Direct reference: DS-000000000012/)).toBeTruthy()
  const attempts = fetch.mock.calls.filter(([url]) => url === '/api/v1/sales/attempts')
  expect(attempts).toHaveLength(2)
  expect(attempts[0][1].body).toBe(attempts[1][1].body)
  expect(attempts[0][1].headers['Idempotency-Key']).toBe(attempts[1][1].headers['Idempotency-Key'])
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
})

it('never sends a reserved Direct sale after the server protocol changes', async () => {
  let selected = 'reserved_v1'
  reservedSetup(cashier, (url) => url === '/api/v1/sales/attempts'
    ? Promise.resolve(reply(201, reservedReply('Direct'))) : null)
  const original = fetch.getMockImplementation()
  fetch.rawImplementation((url, init) => url === '/api/v1/sales/capabilities'
    ? Promise.resolve(reply(200, { protocol: selected })) : original(url, init))
  await ready()
  add('Oil', 'product')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  await screen.findByText(/Direct reference: DS-000000000012/)
  selected = 'legacy'
  fireEvent.click(screen.getByLabelText(/I recorded this Direct reference/i))
  fireEvent.click(screen.getByRole('button', { name: 'Submit reserved sale' }))
  await screen.findByText(/Cannot verify this reserved attempt now/i)
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
  expect(sessionStorage.getItem('yabs-pending-sale')).toBe(JSON.stringify({ key: KEY, userId: 2 }))
})

it('prevents duplicate reserved Direct POSTs while the first remains in flight', async () => {
  const waiting = deferred()
  reservedSetup(cashier, (url) => url === '/api/v1/sales/attempts'
    ? Promise.resolve(reply(201, reservedReply('Direct')))
    : url === '/api/v1/transactions' ? waiting.promise : null)
  await ready()
  add('Oil', 'product')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  await screen.findByText(/Direct reference: DS-000000000012/)
  fireEvent.click(screen.getByLabelText(/I recorded this Direct reference/i))
  const send = screen.getByRole('button', { name: 'Submit reserved sale' })
  fireEvent.click(send)
  fireEvent.click(send)
  await waitFor(() => expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/transactions')).toHaveLength(1))
  waiting.resolve(reply(201, sale))
  await screen.findByRole('heading', { name: 'Sale Confirmed' })
})

it('also supports Owner reservation without exposing Cashier-only assumptions', async () => {
  reservedSetup(owner, (url) => url === '/api/v1/sales/attempts'
    ? Promise.resolve(reply(201, reservedReply('Direct', null, 1))) : null)
  await ready(owner)
  add('Oil', 'product')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  await screen.findByText(/Direct reference: DS-000000000012/)
  expect(sessionStorage.getItem('yabs-pending-sale')).toBe(JSON.stringify({ key: KEY, userId: 1 }))
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
})

it.each([409, 422])('keeps the pending identifier on reservation %i', async (status) => {
  reservedSetup(cashier, (url) => url === '/api/v1/sales/attempts'
    ? Promise.resolve(reply(status, {})) : null)
  await ready()
  add('Oil', 'product')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  await screen.findByText(/Reservation outcome is uncertain/i)
  expect(sessionStorage.getItem('yabs-pending-sale')).toBe(JSON.stringify({ key: KEY, userId: 2 }))
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
  expect(screen.getByRole('button', { name: 'Manual Entry' }).disabled).toBe(true)
})

it('discovers a Reserved attempt after reload but never reconstructs or posts its payload', async () => {
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  reservedSetup(cashier, (url) => url.includes('/by-idempotency-key/')
    ? Promise.resolve(reply(200, { status: 'not_committed_at_check', sale: null })) : null,
  reservedReply('Direct'))
  await ready()
  await screen.findByText(/original sale details are unavailable after reload/i)
  expect(screen.getByRole('button', { name: 'Review sale' }).disabled).toBe(true)
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions' ||
    url === '/api/v1/sales/attempts')).toBe(false)
  expect(sessionStorage.getItem('yabs-pending-sale')).toBe(JSON.stringify({ key: KEY, userId: 2 }))
})

it('blocks a new electronic sale when another tab or device has an open reservation', async () => {
  reservedSetup(cashier, () => null, reservedReply('Direct'))
  await ready()
  expect(await screen.findByText(/An open Direct reservation exists/i)).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Review sale' }).disabled).toBe(true)
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/sales/attempts')).toBe(false)
})

it('shows the Cashier own Manual paper reference without Owner recovery controls', async () => {
  reservedSetup(cashier, () => null, investigationRow(12, 'Reserved', 'Manual'))
  await ready()
  expect(await screen.findByText(/PAPER-20261027-001/)).toBeTruthy()
  expect(screen.getByText(/Contact the Owner to investigate/)).toBeTruthy()
  expect(screen.queryByRole('heading', { name: 'Sale Attempts' })).toBeNull()
  expect(screen.queryByRole('button', { name: /Cancel attempt/ })).toBeNull()
  expect(screen.getByRole('button', { name: 'Review sale' }).disabled).toBe(true)
})

it('manually clears only the exact Cancelled key after reload and never submits a replacement', async () => {
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  sessionStorage.setItem('unrelated-setting', 'preserve')
  const lookup = `/api/v1/sales/attempts/by-idempotency-key/${KEY}`
  reservedSetup(cashier, (url) => url === `/api/v1/transactions/by-idempotency-key/${KEY}`
    ? Promise.resolve(reply(200, { status: 'not_committed_at_check', sale: null }))
    : url === lookup ? Promise.resolve(reply(200, investigationRow(12, 'Cancelled')))
      : null)
  await ready()
  await screen.findByText(/No committed sale found at this check/)
  fireEvent.click(screen.getByRole('button', { name: 'Check cancelled attempt' }))
  const clear = await screen.findByRole('button', { name: 'Clear matching pending identifier' })
  expect(sessionStorage.getItem('yabs-pending-sale')).toBe(JSON.stringify({ key: KEY, userId: 2 }))
  expect(fetch.mock.calls.find(([url]) => url === lookup)[1].cache).toBe('no-store')
  expect(screen.queryByRole('button', { name: 'Retry exact sale' })).toBeNull()
  fireEvent.click(clear)
  expect(await screen.findByText(/cancelled pending identifier was cleared/)).toBeTruthy()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeNull()
  expect(sessionStorage.getItem('unrelated-setting')).toBe('preserve')
  expect(screen.getByText('No items added yet.')).toBeTruthy()
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/transactions' ||
    url === '/api/v1/transactions/manual' || url === '/api/v1/sales/attempts')).toHaveLength(0)
  expect(fetch.mock.calls.filter(([url]) => url === lookup)).toHaveLength(2)
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/sales/attempts/open')).toHaveLength(2)
})

it('discards the in-memory Manual payload and draft after exact Cancelled clearance', async () => {
  reservedSetup(cashier, (url, init) => url === '/api/v1/sales/attempts'
    ? Promise.resolve(reply(201, reservedReply('Manual', JSON.parse(init.body).sale.manual_reference)))
    : url === '/api/v1/transactions/manual' ? Promise.resolve(reply(503, {}))
      : url === `/api/v1/sales/attempts/by-idempotency-key/${KEY}`
        ? Promise.resolve(reply(200, investigationRow(12, 'Cancelled', 'Manual')))
        : url === `/api/v1/transactions/by-idempotency-key/${KEY}`
          ? Promise.resolve(reply(200, { status: 'not_committed_at_check', sale: null })) : null)
  await ready()
  await manualReady()
  fillManualService()
  fireEvent.click(screen.getByRole('button', { name: 'Review Manual sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm Manual sale' }))
  await screen.findByText(/sale outcome is uncertain/i)
  expect(screen.getByRole('button', { name: 'Retry exact sale' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Check cancelled attempt' }))
  const clear = await screen.findByRole('button', { name: 'Clear matching pending identifier' })
  expect(screen.queryByRole('button', { name: 'Retry exact sale' })).toBeNull()
  fireEvent.click(clear)
  expect(await screen.findByText(/cancelled pending identifier was cleared/)).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Direct Sale' }).getAttribute('aria-pressed')).toBe('true')
  expect(screen.getByText('No items added yet.')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Manual Entry' }))
  expect((await screen.findByLabelText('Paper reference')).value).toBe('')
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/transactions/manual')).toHaveLength(1)
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeNull()
})

it.each(['Reserved', 'Committed', 'missing', 'network'])('never clears a %s or unverified attempt', async (state) => {
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  const lookup = `/api/v1/sales/attempts/by-idempotency-key/${KEY}`
  reservedSetup(cashier, (url) => url === `/api/v1/transactions/by-idempotency-key/${KEY}`
    ? Promise.resolve(reply(200, { status: 'not_committed_at_check', sale: null }))
    : url === lookup ? state === 'network' ? Promise.reject(new Error('offline'))
      : Promise.resolve(state === 'missing' ? reply(404, {}) : reply(200, investigationRow(12, state)))
      : null)
  await ready()
  await screen.findByText(/No committed sale found at this check/)
  fireEvent.click(screen.getByRole('button', { name: 'Check cancelled attempt' }))
  await screen.findByText(/not confirmed Cancelled|No matching sale attempt|could not be verified/)
  expect(screen.queryByRole('button', { name: 'Clear matching pending identifier' })).toBeNull()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBe(JSON.stringify({ key: KEY, userId: 2 }))
})

it('does not offer clearance while the same sale key is processing', async () => {
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  let checks = 0
  reservedSetup(cashier, (url) => url === `/api/v1/transactions/by-idempotency-key/${KEY}`
    ? Promise.resolve(reply(200, { status: ++checks === 1 ? 'not_committed_at_check' : 'processing', sale: null }))
    : url === `/api/v1/sales/attempts/by-idempotency-key/${KEY}`
      ? Promise.resolve(reply(200, investigationRow(12, 'Cancelled'))) : null)
  await ready()
  await screen.findByText(/No committed sale found at this check/)
  fireEvent.click(screen.getByRole('button', { name: 'Check cancelled attempt' }))
  expect(await screen.findByText(/Sale key is processing or committed/)).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Clear matching pending identifier' })).toBeNull()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeTruthy()
})

it('keeps the matching pending key when capability changes before clearance', async () => {
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  let capability = 'reserved_v1'
  fetch.rawImplementation((url) => Promise.resolve(url.endsWith('/me') ? reply(200, cashier)
    : url === '/api/v1/sales/capabilities' ? reply(200, { protocol: capability })
      : url === '/api/v1/sales/attempts/open' ? reply(200, null)
        : url === '/api/v1/sales/options' ? reply(200, options)
          : url === `/api/v1/sales/attempts/by-idempotency-key/${KEY}`
            ? reply(200, investigationRow(12, 'Cancelled'))
            : url === `/api/v1/transactions/by-idempotency-key/${KEY}`
              ? reply(200, { status: 'not_committed_at_check', sale: null }) : reply(404, {})))
  await ready()
  await screen.findByText(/No committed sale found at this check/)
  fireEvent.click(screen.getByRole('button', { name: 'Check cancelled attempt' }))
  const clear = await screen.findByRole('button', { name: 'Clear matching pending identifier' })
  capability = 'legacy'
  fireEvent.click(clear)
  expect(await screen.findByText(/clearance was not completed/)).toBeTruthy()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBe(JSON.stringify({ key: KEY, userId: 2 }))
})

it('rejects a changed pending identifier during Cancelled lookup', async () => {
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  const delayed = deferred()
  reservedSetup(cashier, (url) => url === `/api/v1/transactions/by-idempotency-key/${KEY}`
    ? Promise.resolve(reply(200, { status: 'not_committed_at_check', sale: null }))
    : url === `/api/v1/sales/attempts/by-idempotency-key/${KEY}` ? delayed.promise : null)
  await ready()
  await screen.findByText(/No committed sale found at this check/)
  fireEvent.click(screen.getByRole('button', { name: 'Check cancelled attempt' }))
  const other = '3f9ab8b9-e91d-4ea1-9f55-096b958a41db'
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: other, userId: 2 }))
  delayed.resolve(reply(200, investigationRow(12, 'Cancelled')))
  await screen.findByText(/Cancelled state could not be verified/)
  expect(screen.queryByRole('button', { name: 'Clear matching pending identifier' })).toBeNull()
  expect(sessionStorage.getItem('yabs-pending-sale')).toContain(other)
})

it('rechecks the exact browser identifier after an in-flight clearance lookup', async () => {
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  const delayed = deferred()
  let lookups = 0
  reservedSetup(cashier, (url) => url === `/api/v1/transactions/by-idempotency-key/${KEY}`
    ? Promise.resolve(reply(200, { status: 'not_committed_at_check', sale: null }))
    : url === `/api/v1/sales/attempts/by-idempotency-key/${KEY}`
      ? ++lookups === 1 ? Promise.resolve(reply(200, investigationRow(12, 'Cancelled'))) : delayed.promise
      : null)
  await ready()
  await screen.findByText(/No committed sale found at this check/)
  fireEvent.click(screen.getByRole('button', { name: 'Check cancelled attempt' }))
  const clear = await screen.findByRole('button', { name: 'Clear matching pending identifier' })
  fireEvent.click(clear)
  const other = '3f9ab8b9-e91d-4ea1-9f55-096b958a41db'
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: other, userId: 2 }))
  delayed.resolve(reply(200, investigationRow(12, 'Cancelled')))
  expect(await screen.findByText(/clearance was not completed/)).toBeTruthy()
  expect(sessionStorage.getItem('yabs-pending-sale')).toContain(other)
  expect(screen.getByRole('button', { name: 'Review sale' }).disabled).toBe(true)
})

it('does not offer Cashier cancellation clearance for a different signed-in user', async () => {
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 1 }))
  reservedSetup(cashier)
  await ready()
  expect(await screen.findByText(/unresolved sale for another account/)).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Check cancelled attempt' })).toBeNull()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBe(JSON.stringify({ key: KEY, userId: 1 }))
})

it('keeps pending blocked when storage disappears before Cancelled clearance', async () => {
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  reservedSetup(cashier, (url) => url === `/api/v1/transactions/by-idempotency-key/${KEY}`
    ? Promise.resolve(reply(200, { status: 'not_committed_at_check', sale: null }))
    : url === `/api/v1/sales/attempts/by-idempotency-key/${KEY}`
      ? Promise.resolve(reply(200, investigationRow(12, 'Cancelled'))) : null)
  await ready()
  await screen.findByText(/No committed sale found at this check/)
  fireEvent.click(screen.getByRole('button', { name: 'Check cancelled attempt' }))
  const clear = await screen.findByRole('button', { name: 'Clear matching pending identifier' })
  sessionStorage.removeItem('yabs-pending-sale')
  fireEvent.click(clear)
  expect(await screen.findByText(/identifier changed or is unavailable/)).toBeTruthy()
  expect(screen.queryByText(/cancelled pending identifier was cleared/)).toBeNull()
  expect(screen.getByRole('button', { name: 'Review sale' }).disabled).toBe(true)
})

it('fails closed if browser storage refuses to remove a verified Cancelled identifier', async () => {
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  reservedSetup(cashier, (url) => url === `/api/v1/transactions/by-idempotency-key/${KEY}`
    ? Promise.resolve(reply(200, { status: 'not_committed_at_check', sale: null }))
    : url === `/api/v1/sales/attempts/by-idempotency-key/${KEY}`
      ? Promise.resolve(reply(200, investigationRow(12, 'Cancelled'))) : null)
  await ready()
  await screen.findByText(/No committed sale found at this check/)
  fireEvent.click(screen.getByRole('button', { name: 'Check cancelled attempt' }))
  const clear = await screen.findByRole('button', { name: 'Clear matching pending identifier' })
  vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('storage denied') })
  fireEvent.click(clear)
  expect(await screen.findByText(/clearance was not completed/)).toBeTruthy()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBe(JSON.stringify({ key: KEY, userId: 2 }))
  expect(screen.getByRole('button', { name: 'Review sale' }).disabled).toBe(true)
})

it('keeps attempt controls hidden while the server reports legacy sales', () => {
  render(<OwnerSaleReconciliation pendingSale={{ pending: null, protocol: 'legacy', clearAcknowledged: vi.fn() }}
    csrfToken="synthetic-csrf" onRevalidateSession={vi.fn()} />)
  expect(screen.getByRole('button', { name: 'Check sale' })).toBeTruthy()
  expect(screen.queryByRole('heading', { name: 'Sale Attempts' })).toBeNull()
  expect(fetch).not.toHaveBeenCalled()
})

it('validates Owner attempt search and loads bounded pages without exposing payloads', async () => {
  const firstPage = Array.from({ length: 50 }, (_, i) => investigationRow(100 - i))
  fetch.mockImplementation((path) => Promise.resolve(path.includes('/sales/attempts?')
    ? reply(200, path.includes('before_id=51') ? [investigationRow(50, 'Cancelled')] : firstPage)
    : reply(500, {})))
  render(<OwnerSaleReconciliation pendingSale={{ pending: null, protocol: 'reserved_v1', clearAcknowledged: vi.fn() }}
    csrfToken="synthetic-csrf" onRevalidateSession={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Search attempts' }))
  expect(screen.getByText(/Enter a valid recording user ID/)).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Attempt recording user ID'), { target: { value: '2' } })
  fireEvent.change(screen.getByLabelText(/Exact Direct or paper reference/), { target: { value: 'invalid' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search attempts' }))
  expect(fetch.mock.calls.some(([path]) => path.includes('/sales/attempts?'))).toBe(false)
  fireEvent.change(screen.getByLabelText(/Exact Direct or paper reference/),
    { target: { value: ' ds-000000000100 ' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search attempts' }))
  await screen.findByText('Attempt #100')
  expect(fetch.mock.calls.find(([path]) => path.includes('/sales/attempts?'))[0])
    .toContain('reference=DS-000000000100')
  expect(screen.getAllByRole('button', { name: /Cancel attempt/ })).toHaveLength(50)
  fireEvent.click(screen.getByRole('button', { name: 'Load more attempts' }))
  await screen.findByText('Attempt #50')
  expect(fetch.mock.calls.some(([path]) => path.includes('before_id=51'))).toBe(true)
  expect(screen.getByText(/permanently fenced/)).toBeTruthy()
  expect(screen.queryByText(/request.hash|payment.secret|full.payload/i)).toBeNull()
})

it('ignores a stale Owner attempt search after inputs change', async () => {
  const slow = deferred()
  fetch.mockImplementation((path) => path.includes('recording_user_id=2') ? slow.promise
    : Promise.resolve(reply(200, [{ ...investigationRow(20), user_id: 3 }])))
  render(<OwnerSaleReconciliation pendingSale={{ pending: null, protocol: 'reserved_v1', clearAcknowledged: vi.fn() }}
    csrfToken="synthetic-csrf" onRevalidateSession={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('Attempt recording user ID'), { target: { value: '2' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search attempts' }))
  fireEvent.change(screen.getByLabelText('Attempt recording user ID'), { target: { value: '3' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search attempts' }))
  await screen.findByText('Attempt #20')
  slow.resolve(reply(200, [investigationRow(10)]))
  await waitFor(() => expect(screen.queryByText('Attempt #10')).toBeNull())
})

it('requires fresh exact-key lookup for a Committed attempt and leaves Cancelled read-only', async () => {
  fetch.mockImplementation((path) => Promise.resolve(path.includes('/sales/attempts?')
    ? reply(200, [investigationRow(9, 'Committed'), investigationRow(8, 'Cancelled')])
    : reply(500, {})))
  render(<OwnerSaleReconciliation pendingSale={{ pending: null, protocol: 'reserved_v1', clearAcknowledged: vi.fn() }}
    csrfToken="synthetic-csrf" onRevalidateSession={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('Attempt recording user ID'), { target: { value: '2' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search attempts' }))
  await screen.findByText('Attempt #9')
  expect(screen.queryByRole('button', { name: 'Acknowledge committed sale' })).toBeNull()
  expect(screen.queryByRole('button', { name: /Cancel attempt/ })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Use exact-key lookup for attempt #9' }))
  expect(screen.getByLabelText('Recording user ID').value).toBe('2')
  expect(screen.getByLabelText('Exact sale UUID').value).toBe(KEY)
  expect(screen.getByText(/fresh committed lookup/)).toBeTruthy()
  expect(fetch.mock.calls.some(([path]) => path.includes('/acknowledge'))).toBe(false)
})

it('requires evidence, reason, confirmation and fresh detail before one Owner cancellation', async () => {
  const row = investigationRow(12)
  const response = deferred()
  fetch.mockImplementation((path) => path.includes('/sales/attempts?')
    ? Promise.resolve(reply(200, [row]))
    : path === '/api/v1/sales/attempts/12' ? Promise.resolve(reply(200, row))
      : path === '/api/v1/sales/attempts/12/cancel' ? response.promise : Promise.resolve(reply(500, {})))
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  render(<OwnerSaleReconciliation pendingSale={{ pending: null, protocol: 'reserved_v1', clearAcknowledged: vi.fn() }}
    csrfToken="synthetic-csrf" onRevalidateSession={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('Attempt recording user ID'), { target: { value: '2' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search attempts' }))
  await screen.findByText('Attempt #12')
  fireEvent.click(screen.getByRole('button', { name: 'Cancel attempt #12' }))
  let prompt = await screen.findByRole('dialog', { name: 'Cancel reserved attempt #12' })
  expect(document.activeElement).toBe(within(prompt).getByRole('button', { name: 'Keep attempt' }))
  expect(within(prompt).getByRole('button', { name: 'Confirm cancellation' }).disabled).toBe(true)
  fireEvent.click(within(prompt).getByRole('button', { name: 'Keep attempt' }))
  expect(fetch.mock.calls.some(([path]) => path.endsWith('/cancel'))).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Cancel attempt #12' }))
  prompt = await screen.findByRole('dialog', { name: 'Cancel reserved attempt #12' })
  const escape = new window.Event('cancel', { cancelable: true })
  fireEvent(prompt, escape)
  expect(escape.defaultPrevented).toBe(true)
  expect(fetch.mock.calls.some(([path]) => path.endsWith('/cancel'))).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Cancel attempt #12' }))
  prompt = await screen.findByRole('dialog', { name: 'Cancel reserved attempt #12' })
  fireEvent.change(within(prompt).getByLabelText('Cancellation reason'), { target: { value: '   ' } })
  fireEvent.click(within(prompt).getByLabelText(/I verified the external receipt/))
  expect(within(prompt).getByRole('button', { name: 'Confirm cancellation' }).disabled).toBe(true)
  fireEvent.change(within(prompt).getByLabelText('Cancellation reason'), { target: { value: 'x'.repeat(501) } })
  expect(within(prompt).getByRole('button', { name: 'Confirm cancellation' }).disabled).toBe(true)
  fireEvent.change(within(prompt).getByLabelText('Cancellation reason'), { target: { value: '  Verified duplicate  ' } })
  const confirm = within(prompt).getByRole('button', { name: 'Confirm cancellation' })
  fireEvent.click(confirm)
  fireEvent.click(confirm)
  expect(confirm.disabled).toBe(true)
  await waitFor(() => expect(fetch.mock.calls.filter(([path]) => path.endsWith('/cancel'))).toHaveLength(1))
  expect(fetch.mock.calls.filter(([path]) => path === '/api/v1/sales/attempts/12')).toHaveLength(4)
  const [, request] = fetch.mock.calls.find(([path]) => path.endsWith('/cancel'))
  expect(request.headers['X-CSRF-Token']).toBe('synthetic-csrf')
  expect(JSON.parse(request.body)).toEqual({ reason: 'Verified duplicate', evidence_verified: true })
  response.resolve(reply(200, { ...row, state: 'Cancelled' }))
  expect(await screen.findByText(/Its key and reference remain fenced/)).toBeTruthy()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBe(JSON.stringify({ key: KEY, userId: 2 }))
})

it.each([401, 403, 409, 422, 500])('keeps browser pending state after cancellation response %i', async (code) => {
  const row = investigationRow(12)
  const onRevalidateSession = vi.fn()
  fetch.mockImplementation((path) => Promise.resolve(path.includes('/sales/attempts?')
    ? reply(200, [row]) : path === '/api/v1/sales/attempts/12' ? reply(200, row)
      : path.endsWith('/cancel') ? reply(code, {}) : reply(500, {})))
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  render(<OwnerSaleReconciliation pendingSale={{ pending: null, protocol: 'reserved_v1', clearAcknowledged: vi.fn() }}
    csrfToken="synthetic-csrf" onRevalidateSession={onRevalidateSession} />)
  fireEvent.change(screen.getByLabelText('Attempt recording user ID'), { target: { value: '2' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search attempts' }))
  await screen.findByText('Attempt #12')
  fireEvent.click(screen.getByRole('button', { name: 'Cancel attempt #12' }))
  const prompt = await screen.findByRole('dialog', { name: 'Cancel reserved attempt #12' })
  fireEvent.change(within(prompt).getByLabelText('Cancellation reason'), { target: { value: 'Verified evidence' } })
  fireEvent.click(within(prompt).getByLabelText(/I verified the external receipt/))
  fireEvent.click(within(prompt).getByRole('button', { name: 'Confirm cancellation' }))
  const detailCount = code === 409 || code === 500 ? 3 : 2
  await waitFor(() => expect(fetch.mock.calls.filter(([path]) => path === '/api/v1/sales/attempts/12')).toHaveLength(detailCount))
  if (code === 401) await waitFor(() => expect(onRevalidateSession).toHaveBeenCalledTimes(1))
  expect(sessionStorage.getItem('yabs-pending-sale')).toBe(JSON.stringify({ key: KEY, userId: 2 }))
  expect(screen.getByRole('button', { name: 'Cancel attempt #12' })).toBeTruthy()
})

it('does not send cancellation if a Reserved attempt changed before confirmation', async () => {
  const row = investigationRow(12)
  let detailChecks = 0
  fetch.mockImplementation((path) => Promise.resolve(path.includes('/sales/attempts?')
    ? reply(200, [row]) : path === '/api/v1/sales/attempts/12'
      ? reply(200, ++detailChecks === 1 ? row : { ...row, state: 'Committed' }) : reply(500, {})))
  render(<OwnerSaleReconciliation pendingSale={{ pending: null, protocol: 'reserved_v1', clearAcknowledged: vi.fn() }}
    csrfToken="synthetic-csrf" onRevalidateSession={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('Attempt recording user ID'), { target: { value: '2' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search attempts' }))
  await screen.findByText('Attempt #12')
  fireEvent.click(screen.getByRole('button', { name: 'Cancel attempt #12' }))
  const prompt = await screen.findByRole('dialog', { name: 'Cancel reserved attempt #12' })
  fireEvent.change(within(prompt).getByLabelText('Cancellation reason'), { target: { value: 'Evidence checked' } })
  fireEvent.click(within(prompt).getByLabelText(/I verified the external receipt/))
  fireEvent.click(within(prompt).getByRole('button', { name: 'Confirm cancellation' }))
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Cancel reserved attempt #12' })).toBeNull())
  expect(fetch.mock.calls.some(([path]) => path.endsWith('/cancel'))).toBe(false)
  expect(await screen.findByRole('button', { name: 'Use exact-key lookup for attempt #12' })).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Cancel attempt #12' })).toBeNull()
})

it('requires fresh Owner acknowledgment before clearing an exact cross-user pending identifier', async () => {
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  const committed = { ...sale, recorded_by_user_id: 2, status: 'Completed' }
  const url = `/api/v1/transactions/reconciliation/2/${KEY}`
  fetch.mockImplementation((path) => Promise.resolve(path.endsWith('/me') ? reply(200, owner)
    : path.endsWith('/staff') ? reply(200, [])
      : path.endsWith('/sales/options') ? reply(200, options)
        : path === url ? reply(200, { status: 'committed', sale: committed })
          : path === url + '/acknowledge' ? reply(200, { status: 'committed',
            recording_user_id: 2, idempotency_key: KEY, sale: committed }) : reply(404, {})))
  await ready(owner)
  expect(screen.getByLabelText('Recording user ID').value).toBe('2')
  expect(screen.getByLabelText('Exact sale UUID').value).toBe(KEY)
  fireEvent.click(screen.getByRole('button', { name: 'Check sale' }))
  expect(await screen.findByText(/Transaction #11 — Completed/)).toBeTruthy()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Acknowledge committed sale' }))
  const confirmation = screen.getByRole('dialog', { name: 'Acknowledge transaction #11' })
  expect(within(confirmation).getByText(/matching pending identifier/i)).toBeTruthy()
  expect(document.activeElement).toBe(within(confirmation).getByRole('button', { name: 'Cancel' }))
  expect(fetch.mock.calls.some(([path]) => path === url + '/acknowledge')).toBe(false)
  fireEvent.click(within(confirmation).getByRole('button', { name: 'Confirm acknowledgment' }))
  expect(await screen.findByText(/Matching pending identifier cleared/i)).toBeTruthy()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeNull()
  expect(fetch.mock.calls.find(([path]) => path === url + '/acknowledge')[1].headers['X-CSRF-Token']).toBe('synthetic-csrf')
  expect(fetch.mock.calls.some(([path]) => path === '/api/v1/transactions')).toBe(false)
})

it('never clears pending for uncertain lookup, failed acknowledgment, or a different key', async () => {
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  const other = '3f9ab8b9-e91d-4ea1-9f55-096b958a41db'
  let status = 'processing'
  fetch.mockImplementation((path) => Promise.resolve(path.endsWith('/me') ? reply(200, owner)
    : path.endsWith('/staff') ? reply(200, [])
      : path.endsWith('/sales/options') ? reply(200, options)
        : path.includes('/reconciliation/') && path.endsWith('/acknowledge')
          ? (status === 'failed' ? reply(409, {}) : reply(200, { status: 'committed',
            recording_user_id: 2, idempotency_key: other, sale: { ...sale, recorded_by_user_id: 2 } }))
          : reply(200, status === 'committed' || status === 'failed'
            ? { status: 'committed', sale: { ...sale, recorded_by_user_id: 2 } }
            : { status, sale: null })))
  await ready(owner)
  fireEvent.click(screen.getByRole('button', { name: 'Check sale' }))
  expect(await screen.findByText(/Sale key is processing/)).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Acknowledge committed sale' })).toBeNull()
  status = 'not_committed_at_check'
  fireEvent.click(screen.getByRole('button', { name: 'Check sale' }))
  expect(await screen.findByText(/A delayed request may still commit/)).toBeTruthy()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeTruthy()
  status = 'failed'
  fireEvent.click(screen.getByRole('button', { name: 'Check sale' }))
  await screen.findByText(/Transaction #11/)
  fireEvent.click(screen.getByRole('button', { name: 'Acknowledge committed sale' }))
  fireEvent.click(within(screen.getByRole('dialog', { name: 'Acknowledge transaction #11' }))
    .getByRole('button', { name: 'Confirm acknowledgment' }))
  expect(await screen.findByText(/Sale is not confirmed committed/)).toBeTruthy()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeTruthy()
  status = 'committed'
  fireEvent.change(screen.getByLabelText('Exact sale UUID'), { target: { value: other } })
  fireEvent.click(screen.getByRole('button', { name: 'Check sale' }))
  await screen.findByText(/Transaction #11/)
  fireEvent.click(screen.getByRole('button', { name: 'Acknowledge committed sale' }))
  fireEvent.click(within(screen.getByRole('dialog', { name: 'Acknowledge transaction #11' }))
    .getByRole('button', { name: 'Confirm acknowledgment' }))
  expect(await screen.findByText(/No matching pending identifier/i)).toBeTruthy()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeTruthy()
})

it('cancels with button or Escape and invalidates confirmation when investigation changes', async () => {
  const url = `/api/v1/transactions/reconciliation/2/${KEY}`
  const committed = { ...sale, recorded_by_user_id: 2, status: 'Completed' }
  fetch.mockImplementation((path) => Promise.resolve(path === url
    ? reply(200, { status: 'committed', sale: committed }) : reply(500, {})))
  render(<OwnerSaleReconciliation pendingSale={{ pending: { userId: 2, key: KEY }, clearAcknowledged: vi.fn() }}
    csrfToken="synthetic-csrf" onRevalidateSession={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check sale' }))
  await screen.findByText(/Transaction #11/)
  fireEvent.click(screen.getByRole('button', { name: 'Acknowledge committed sale' }))
  let prompt = screen.getByRole('dialog', { name: 'Acknowledge transaction #11' })
  fireEvent.click(within(prompt).getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Acknowledge committed sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Acknowledge committed sale' }))
  prompt = screen.getByRole('dialog', { name: 'Acknowledge transaction #11' })
  const escapeCancel = new window.Event('cancel', { cancelable: true })
  fireEvent(prompt, escapeCancel)
  expect(escapeCancel.defaultPrevented).toBe(true)
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(fetch.mock.calls.some(([path]) => path === url + '/acknowledge')).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Acknowledge committed sale' }))
  fireEvent.change(screen.getByLabelText('Exact sale UUID'), { target: { value: 'changed' } })
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Acknowledge committed sale' })).toBeNull()
  expect(fetch.mock.calls.some(([path]) => path === url + '/acknowledge')).toBe(false)
})

it('sends one acknowledgment while pending and leaves browser state blocked on failure', async () => {
  const url = `/api/v1/transactions/reconciliation/2/${KEY}`
  const response = deferred()
  const clearAcknowledged = vi.fn()
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  fetch.mockImplementation((path) => path === url + '/acknowledge' ? response.promise
    : Promise.resolve(reply(200, { status: 'committed', sale: { ...sale, recorded_by_user_id: 2 } })))
  render(<OwnerSaleReconciliation pendingSale={{ pending: { userId: 2, key: KEY }, clearAcknowledged }}
    csrfToken="synthetic-csrf" onRevalidateSession={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check sale' }))
  await screen.findByText(/Transaction #11/)
  fireEvent.click(screen.getByRole('button', { name: 'Acknowledge committed sale' }))
  const prompt = screen.getByRole('dialog', { name: 'Acknowledge transaction #11' })
  const confirm = within(prompt).getByRole('button', { name: 'Confirm acknowledgment' })
  fireEvent.click(confirm)
  fireEvent.click(confirm)
  expect(confirm.disabled).toBe(true)
  expect(fetch.mock.calls.filter(([path]) => path === url + '/acknowledge')).toHaveLength(1)
  const escapeCancel = new window.Event('cancel', { cancelable: true })
  fireEvent(prompt, escapeCancel)
  expect(escapeCancel.defaultPrevented).toBe(true)
  expect(screen.getByRole('dialog', { name: 'Acknowledge transaction #11' })).toBeTruthy()
  response.resolve(reply(409, {}))
  expect(await screen.findByText(/Sale is not confirmed committed/)).toBeTruthy()
  expect(clearAcknowledged).not.toHaveBeenCalled()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBe(JSON.stringify({ key: KEY, userId: 2 }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Acknowledge committed sale' })).toBeNull()
})

it('warns before leaving an unsent Direct draft; cancel preserves it and confirmation discards it', async () => {
  setup(cashier, (url) => url.startsWith('/api/v1/transactions?')
    ? reply(200, { items: [], next_cursor: null }) : reply(200, { status: 'committed', sale }))
  await ready()
  add('Cut')
  fireEvent.click(screen.getByRole('button', { name: 'History' }))
  const prompt = screen.getByRole('dialog', { name: 'Leave Sales?' })
  expect(screen.queryByRole('heading', { name: 'Transaction History' })).toBeNull()
  fireEvent.click(within(prompt).getByRole('button', { name: 'Keep draft' }))
  expect(currentSaleNames()).toEqual(['Cut'])
  fireEvent.click(screen.getByRole('button', { name: 'History' }))
  fireEvent.click(within(screen.getByRole('dialog', { name: 'Leave Sales?' }))
    .getByRole('button', { name: 'Discard draft and leave' }))
  expect(await screen.findByRole('heading', { name: 'Transaction History' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Sales' }))
  expect(await screen.findByText('No items added yet.')).toBeTruthy()
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
})

it('warns before leaving an unsent Manual draft without persisting it', async () => {
  setup(cashier, (url) => url.endsWith('/sales/manual-options') ? reply(200, manualOptions)
    : reply(200, { items: [], next_cursor: null }))
  await ready()
  await manualReady()
  fireEvent.change(screen.getByLabelText('Paper reference'), { target: { value: 'PAPER-20261023-001' } })
  fireEvent.click(screen.getByRole('button', { name: 'Reports' }))
  expect(screen.getByRole('dialog', { name: 'Leave Sales?' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Keep draft' }))
  expect(screen.getByLabelText('Paper reference').value).toBe('PAPER-20261023-001')
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeNull()
})

it('preserves Direct and Manual unsent drafts independently across mode switches', async () => {
  setup(cashier, (url) => url.endsWith('/sales/manual-options') ? reply(200, manualOptions)
    : reply(200, { status: 'not_committed_at_check', sale: null }))
  await ready()
  add('Cut')
  await manualReady()
  fireEvent.change(screen.getByLabelText('Paper reference'), { target: { value: 'PAPER-20261023-001' } })
  fireEvent.click(screen.getByRole('button', { name: 'Direct Sale' }))
  expect(currentSaleNames()).toEqual(['Cut'])
  fireEvent.click(screen.getByRole('button', { name: 'Manual Entry' }))
  expect(screen.getByLabelText('Paper reference').value).toBe('PAPER-20261023-001')
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions/manual')).toBe(false)
})

it('submits Manual to its original endpoint and uses the shared unresolved guard for exact retry', async () => {
  const posts = []
  setup(cashier, (url) => {
    if (url.endsWith('/sales/manual-options')) return reply(200, manualOptions)
    if (url === '/api/v1/transactions/manual') { posts.push(url); return reply(503, {}) }
    return reply(200, { status: 'not_committed_at_check', sale: null })
  })
  await ready()
  await manualReady()
  fillManualService()
  fireEvent.click(screen.getByRole('button', { name: 'Review Manual sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm Manual sale' }))
  await screen.findByText(/sale outcome is uncertain/i)
  expect(screen.getByRole('button', { name: 'Direct Sale' }).disabled).toBe(true)
  expect(sessionStorage.getItem('yabs-pending-sale')).toBe(JSON.stringify({ key: KEY, userId: 2 }))
  fireEvent.click(screen.getByRole('button', { name: 'Retry exact sale' }))
  await waitFor(() => expect(posts).toHaveLength(2))
  const attempts = fetch.mock.calls.filter(([url]) => url === '/api/v1/transactions/manual')
  expect(attempts[0][1].body).toBe(attempts[1][1].body)
  expect(attempts[0][1].headers['Idempotency-Key']).toBe(attempts[1][1].headers['Idempotency-Key'])
  expect(attempts[0][1].headers['X-CSRF-Token']).toBe('synthetic-csrf')
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions')).toBe(false)
})

it.each([200, 201])('confirms Manual POST %i with backend totals, then clears only its draft', async (status) => {
  setup(cashier, (url) => url.endsWith('/sales/manual-options') ? reply(200, manualOptions)
    : url === '/api/v1/transactions/manual' ? reply(status, sale)
      : reply(200, { status: 'committed', sale }))
  await ready()
  add('Cut')
  await manualReady()
  fillManualService()
  fireEvent.click(screen.getByRole('button', { name: 'Review Manual sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm Manual sale' }))
  expect(await screen.findByText('Sale Confirmed')).toBeTruthy()
  expect(screen.getByText('Staff Commission').nextElementSibling.textContent).toBe('₱51.00')
  expect(screen.getByText('Business Share').nextElementSibling.textContent).toBe('₱130.25')
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'New Sale' }))
  expect(screen.getByLabelText('Paper reference').value).toBe('')
  expect(screen.getByText('No items added yet.')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Direct Sale' }))
  expect(currentSaleNames()).toEqual(['Cut'])
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/transactions/manual')).toHaveLength(1)
})

it('blocks both entry modes after reload with an unresolved pending key', async () => {
  sessionStorage.setItem('yabs-pending-sale', JSON.stringify({ key: KEY, userId: 2 }))
  setup(cashier, (url) => reply(202, { status: 'processing', sale: null }))
  await ready()
  expect(screen.getByRole('button', { name: 'Manual Entry' }).disabled).toBe(true)
  expect(screen.queryByRole('button', { name: 'Retry exact sale' })).toBeNull()
  expect(fetch.mock.calls.some(([url]) => url === '/api/v1/transactions/manual')).toBe(false)
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeTruthy()
})

it.each([403, 409, 422])('keeps a Manual attempt unresolved after POST %i', async (status) => {
  setup(cashier, (url) => url.endsWith('/sales/manual-options') ? reply(200, manualOptions)
    : url === '/api/v1/transactions/manual' ? reply(status, {})
      : reply(200, { status: 'not_committed_at_check', sale: null }))
  await ready()
  await manualReady()
  fillManualService()
  fireEvent.click(screen.getByRole('button', { name: 'Review Manual sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm Manual sale' }))
  await screen.findByRole('button', { name: 'Retry exact sale' })
  expect(screen.getByRole('button', { name: 'Direct Sale' }).disabled).toBe(true)
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'New Sale' })).toBeNull()
})

it('shows Owner Sales section without reauth and keeps management sections', async () => {
  setup(owner)
  render(<App />)
  await screen.findByRole('heading', { name: 'Staff Management' })
  fireEvent.click(screen.getByRole('button', { name: 'Sales' }))
  expect(await screen.findByRole('heading', { name: 'Sales Recording' })).toBeTruthy()
  expect(screen.queryByLabelText(/Default Barber/)).toBeNull()
  await screen.findByRole('button', { name: 'Add Cut, ₱101.00' })
  add('Cut')
  expect(screen.getByLabelText('Selling price').disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Remove Cut line 1' }))
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
  expect(screen.queryAllByLabelText('Selling price')).toHaveLength(0)
  expect(screen.getByRole('region', { name: 'Current Sale' }).querySelectorAll('.sales-line-price')).toHaveLength(2)
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

it('defaults new Cashier services and products while allowing per-line uncredited products', async () => {
  const staffOptions = { ...options, staff: [...options.staff, { id: 8, name: 'Ben', role: 'Barber' }] }
  fetch.mockImplementation((url) => Promise.resolve(url.endsWith('/me') ? reply(200, cashier)
    : url === '/api/v1/sales/options' ? reply(200, staffOptions)
      : url === '/api/v1/transactions' ? reply(201, sale) : reply(200, { status: 'committed', sale })))
  await ready()
  const defaultStaff = screen.getByLabelText(/Default Barber/)
  expect(defaultStaff.value).toBe('')
  fireEvent.change(defaultStaff, { target: { value: '4' } })
  add('Cut')
  add('Cut')
  fireEvent.change(screen.getAllByLabelText('Staff')[1], { target: { value: '8' } })
  fireEvent.change(defaultStaff, { target: { value: '8' } })
  add('Color')
  add('Oil', 'product')
  expect(screen.getAllByLabelText('Staff').map((field) => field.value)).toEqual(['4', '8', '8', '8'])
  fireEvent.change(screen.getAllByLabelText('Staff')[3], { target: { value: '' } })
  add('Oil', 'product')
  expect(screen.getAllByLabelText('Staff').map((field) => field.value)).toEqual(['4', '8', '8', '', '8'])
  expect(screen.getByRole('region', { name: 'Current Sale' }).querySelectorAll('.sales-line-price')).toHaveLength(4)
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  expect(screen.getByText('Cut — Ana')).toBeTruthy()
  expect(screen.getByText('Cut — Ben')).toBeTruthy()
  expect(screen.getByText('Color — Ben')).toBeTruthy()
  expect(screen.getByText('Oil — No credited Staff')).toBeTruthy()
  expect(screen.getByText('Oil — Ben')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  await screen.findByText('Sale Confirmed')
  const post = fetch.mock.calls.find(([url]) => url === '/api/v1/transactions')
  expect(JSON.parse(post[1].body).items).toEqual([
    { service_id: 5, staff_id: 4, selling_price: '101.00' },
    { service_id: 5, staff_id: 8, selling_price: '101.00' },
    { service_id: 6, staff_id: 8, selling_price: '120.00' },
    { product_id: 7, selling_price: '80.25' },
    { product_id: 7, staff_id: 8, selling_price: '80.25' },
  ])
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
  await waitFor(() => expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/transactions')).toHaveLength(1))
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

it('blocks Owner section switches while a submitted sale is unresolved', async () => {
  setup(owner, (url) => url === '/api/v1/transactions'
    ? Promise.reject(new Error('offline')) : reply(200, { status: 'not_committed_at_check', sale: null }))
  await ready(owner)
  add('Oil', 'product')
  fireEvent.click(screen.getByRole('button', { name: 'Review sale' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm sale' }))
  await screen.findByRole('button', { name: 'Retry exact sale' })
  fireEvent.click(screen.getByRole('button', { name: 'Staff' }))
  expect(screen.queryByRole('heading', { name: 'Staff Management' })).toBeNull()
  expect(screen.getByText('Resolve the pending sale before leaving Sales.')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Retry exact sale' })).toBeTruthy()
  expect(sessionStorage.getItem('yabs-pending-sale')).toBeTruthy()
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
  expect(currentSaleNames()).toEqual(['Cut'])
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
  expect(currentSaleNames()).toEqual(['Cut', 'Cut'])
  expect(screen.getByText('2 items')).toBeTruthy()
  const remove = screen.getByRole('button', { name: 'Remove Cut line 1' })
  expect(remove.textContent).toBe('×')
  expect(screen.queryByText('Remove')).toBeNull()
  expect(within(screen.getByRole('region', { name: 'Current Sale' })).queryByText('Staff')).toBeNull()
  expect(screen.getAllByLabelText('Staff')).toHaveLength(2)
  expect(screen.getByText('₱202.00')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Remove Cut line 1' }))
  expect(screen.getAllByLabelText('Staff')).toHaveLength(1)
  expect(within(screen.getByRole('region', { name: 'Current Sale' })).getAllByText('₱101.00')).toHaveLength(2)
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
  expect(screen.getAllByLabelText('Selling price')).toHaveLength(1)
  expect(screen.getByRole('region', { name: 'Current Sale' }).querySelector('.sales-line-price').textContent).toBe('₱80.25')
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
  expect(currentSaleNames()).toEqual([longName])
  fireEvent.click(screen.getByRole('button', { name: 'Products' }))
  expect(screen.getByText('No active products are available.')).toBeTruthy()
})
