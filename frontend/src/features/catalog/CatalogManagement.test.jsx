// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'

import CatalogManagement from './CatalogManagement.jsx'

const services = [
  { id: 8, name: 'Color', current_price: '250.00', allows_variable_price: true, commission_rule_id: 1, active: false },
  { id: 2, name: 'Haircut', current_price: '100.00', allows_variable_price: false, commission_rule_id: 1, active: true },
]
const products = [
  { id: 5, name: 'Shampoo', current_price: '100.00', commission_rule_id: 2, active: true },
]
const rules = [
  { id: 1, name: 'Haircut split', type: 'Percentage', value: '50.00', active: true },
  { id: 2, name: 'Product credit', type: 'Fixed', value: '25.00', active: true },
  { id: 3, name: 'Old product credit', type: 'Fixed', value: '10.00', active: false },
]
const response = (status, body = null) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
const mount = (onRevalidateSession = vi.fn()) => render(
  <CatalogManagement csrfToken="synthetic-csrf" onRevalidateSession={onRevalidateSession} />,
)
function seed(nextServices = services, nextProducts = products, nextRules = rules) {
  fetch.mockImplementation((url) => Promise.resolve(response(200,
    url === '/api/v1/services' ? nextServices : url === '/api/v1/products' ? nextProducts : nextRules,
  )))
}
function change(label, value) {
  const dialog = screen.queryByRole('dialog', { name: /^(Add|Edit) (Service|Product)$/ })
  fireEvent.change(dialog ? within(dialog).getByLabelText(label) : screen.getByLabelText(label), { target: { value } })
}
function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
  HTMLDialogElement.prototype.showModal = function () { this.open = true }
  HTMLDialogElement.prototype.close = function () { this.open = false }
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('shows ID-ordered services, switches cached tabs, and filters names and status', async () => {
  seed()
  mount()
  expect(await screen.findByText('Haircut')).toBeTruthy()
  expect([...document.querySelectorAll('.catalog-table tbody tr td:first-child')].map((cell) => cell.textContent))
    .toEqual(['Haircut', 'Color'])
  expect(document.querySelectorAll('.catalog-table thead th')).toHaveLength(5)
  expect(document.querySelector('.catalog-table td[data-label="Commission Rule"]')).toBeTruthy()
  expect(screen.getByText('₱100.00')).toBeTruthy()
  const serviceSearch = screen.getByLabelText('Name')
  expect(serviceSearch.getAttribute('placeholder')).toBe('Search')
  expect(serviceSearch.parentElement.querySelector('svg[aria-hidden="true"]')).toBeTruthy()
  change('Name', 'COLOR')
  expect(screen.queryByText('Haircut')).toBeNull()
  expect(screen.getByText('Color')).toBeTruthy()
  change('Status', 'active')
  expect(screen.getByText('No items match your search or filter.')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Products' }))
  expect(screen.getByText('Shampoo')).toBeTruthy()
  const productSearch = screen.getByLabelText('Name')
  expect(productSearch.getAttribute('placeholder')).toBe('Search')
  expect(productSearch.parentElement.querySelector('svg[aria-hidden="true"]')).toBeTruthy()
  expect(screen.queryByText('Color')).toBeNull()
  expect(screen.getByRole('button', { name: 'Products' }).getAttribute('aria-pressed')).toBe('true')
  expect(fetch).toHaveBeenCalledTimes(3)
  expect(fetch.mock.calls.map(([url]) => url)).toEqual([
    '/api/v1/services', '/api/v1/products', '/api/v1/commission-rules',
  ])
  expect(fetch.mock.calls.every(([, options]) => options.credentials === 'same-origin')).toBe(true)
})

it('creates a service with its variable-price flag, active Percentage rule, decimal string, and CSRF', async () => {
  seed([], [], rules)
  mount()
  await screen.findByText('No services yet.')
  fireEvent.click(screen.getByRole('button', { name: 'Add Service' }))
  const dialog = screen.getByRole('dialog', { name: 'Add Service' })
  expect(dialog.open).toBe(true)
  expect(screen.getByLabelText('Allow Variable Pricing')).toBeTruthy()
  expect([...screen.getByLabelText('Commission Rule').options].map((option) => option.textContent))
    .toEqual(['Select an active Percentage rule', 'Haircut split'])
  change('Name', '  Hair wash  ')
  change('Current Price', '75.50')
  change('Commission Rule', '1')
  fireEvent.click(screen.getByLabelText('Allow Variable Pricing'))
  fetch.mockResolvedValueOnce(response(201, { id: 10, name: 'Hair wash', current_price: '75.50',
    allows_variable_price: true, commission_rule_id: 1, active: true }))
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByText('Hair wash')).toBeTruthy()
  expect(fetch.mock.calls[3]).toEqual(['/api/v1/services', {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'synthetic-csrf' },
    body: JSON.stringify({ name: 'Hair wash', current_price: '75.50', commission_rule_id: 1, allows_variable_price: true }),
  }])
})

it('edits products without Service-only fields and sends only changed configuration', async () => {
  seed()
  mount()
  await screen.findByText('Haircut')
  fireEvent.click(screen.getByRole('button', { name: 'Products' }))
  fireEvent.click(screen.getByRole('button', { name: 'Edit Shampoo' }))
  expect(screen.getByRole('dialog', { name: 'Edit Product' })).toBeTruthy()
  expect(screen.queryByLabelText('Allow Variable Pricing')).toBeNull()
  expect([...screen.getByLabelText('Commission Rule').options].map((option) => option.textContent))
    .toEqual(['Select an active Fixed rule', 'Product credit'])
  change('Current Price', '125.00')
  fetch.mockResolvedValueOnce(response(200, { ...products[0], current_price: '125.00' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await screen.findByText('₱125.00')
  expect(JSON.parse(fetch.mock.calls[3][1].body)).toEqual({ current_price: '125.00' })
  expect(fetch.mock.calls[3][0]).toBe('/api/v1/products/5')
})

it('shows an inactive current rule on an inactive item and allows unrelated edits without reassignment', async () => {
  seed([], [{ ...products[0], active: false, commission_rule_id: 3 }])
  mount()
  await screen.findByText('No services yet.')
  fireEvent.click(screen.getByRole('button', { name: 'Products' }))
  expect(screen.getByText('Old product credit (Inactive)')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Edit Shampoo' }))
  const select = screen.getByLabelText('Commission Rule')
  expect(select.value).toBe('3')
  expect([...select.options].find((option) => option.value === '3').disabled).toBe(true)
  change('Name', 'Shampoo new')
  fetch.mockResolvedValueOnce(response(200, { ...products[0], name: 'Shampoo new', active: false, commission_rule_id: 3 }))
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByText('Shampoo new')).toBeTruthy()
  expect(JSON.parse(fetch.mock.calls[3][1].body)).toEqual({ name: 'Shampoo new' })
  fireEvent.click(screen.getByRole('button', { name: 'Activate Shampoo new' }))
  expect(screen.getByText('Assign an active compatible commission rule before reactivating.')).toBeTruthy()
  expect(fetch).toHaveBeenCalledTimes(4)
})

it('explains missing compatible rules and does not submit an invalid new assignment', async () => {
  seed([], [], rules.filter((rule) => rule.type === 'Fixed'))
  mount()
  await screen.findByText('No services yet.')
  fireEvent.click(screen.getByRole('button', { name: 'Add Service' }))
  expect(screen.getByText(/No active Percentage rules are available/)).toBeTruthy()
  change('Name', 'Cut')
  change('Current Price', '100')
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(screen.getByText('Select a commission rule.')).toBeTruthy()
  expect(fetch).toHaveBeenCalledTimes(3)
})

it.each(['0', '-1', '1.001', 'abc', '10000000000'])('rejects invalid price %s without writing', async (value) => {
  seed()
  mount()
  await screen.findByText('Haircut')
  fireEvent.click(screen.getByRole('button', { name: 'Add Service' }))
  change('Name', 'Cut')
  change('Current Price', value)
  change('Commission Rule', '1')
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(screen.getByLabelText('Current Price').getAttribute('aria-invalid')).toBe('true')
  expect(fetch).toHaveBeenCalledTimes(3)
})

it('blocks an active Product price below its Fixed commission', async () => {
  seed()
  mount()
  await screen.findByText('Haircut')
  fireEvent.click(screen.getByRole('button', { name: 'Products' }))
  fireEvent.click(screen.getByRole('button', { name: 'Edit Shampoo' }))
  change('Current Price', '24.99')
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(screen.getByText('Price must cover the fixed commission.')).toBeTruthy()
  expect(fetch).toHaveBeenCalledTimes(3)
})

it('does not reactivate a Product whose fixed commission exceeds its price', async () => {
  seed([], [{ ...products[0], active: false, current_price: '20.00' }])
  mount()
  await screen.findByText('No services yet.')
  fireEvent.click(screen.getByRole('button', { name: 'Products' }))
  fireEvent.click(screen.getByRole('button', { name: 'Activate Shampoo' }))
  expect(screen.getByText('Product price must cover its fixed commission before reactivating.')).toBeTruthy()
  expect(fetch).toHaveBeenCalledTimes(3)
})

it('requires deactivation confirmation, then activates directly with CSRF', async () => {
  seed()
  mount()
  await screen.findByText('Haircut')
  fireEvent.click(screen.getByRole('button', { name: 'Deactivate Haircut' }))
  expect(screen.getByText(/Historical transaction records will remain unchanged/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(fetch).toHaveBeenCalledTimes(3)
  fireEvent.click(screen.getByRole('button', { name: 'Deactivate Haircut' }))
  fetch.mockResolvedValueOnce(response(200, { ...services[1], active: false }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm deactivation' }))
  await screen.findByText('Haircut deactivated.')
  expect(fetch.mock.calls[3]).toEqual(['/api/v1/services/2/status', {
    method: 'PATCH', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'synthetic-csrf' },
    body: JSON.stringify({ active: false }),
  }])
  fetch.mockResolvedValueOnce(response(200, services[1]))
  fireEvent.click(screen.getByRole('button', { name: 'Activate Haircut' }))
  await screen.findByText('Haircut activated.')
  expect(JSON.parse(fetch.mock.calls[4][1].body)).toEqual({ active: true })
})

it('prevents duplicate saves and shows no success before the backend response', async () => {
  seed([], [], rules)
  mount()
  await screen.findByText('No services yet.')
  fireEvent.click(screen.getByRole('button', { name: 'Add Service' }))
  change('Name', 'Cut')
  change('Current Price', '100')
  change('Commission Rule', '1')
  const wait = deferred()
  fetch.mockImplementationOnce(() => wait.promise)
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  fireEvent.submit(screen.getByRole('button', { name: 'Saving…' }).closest('form'))
  expect(fetch).toHaveBeenCalledTimes(4)
  expect(screen.queryByText('Cut')).toBeNull()
  wait.resolve(response(201, { ...services[1], name: 'Cut' }))
  expect(await screen.findByText('Cut')).toBeTruthy()
})

it('revalidates a 401 and keeps retry available for a temporary load failure', async () => {
  const revalidate = vi.fn().mockResolvedValue(false)
  fetch.mockResolvedValueOnce(response(401)).mockResolvedValueOnce(response(200, products))
    .mockResolvedValueOnce(response(200, rules))
  mount(revalidate)
  await waitFor(() => expect(revalidate).toHaveBeenCalledTimes(1))
})

it('shows a permission error when catalog loading is forbidden', async () => {
  fetch.mockResolvedValueOnce(response(403)).mockResolvedValueOnce(response(200, products))
    .mockResolvedValueOnce(response(200, rules))
  mount()
  expect(await screen.findByText('You do not have permission to manage the catalog.')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy()
})

it('retains the active row and confirmation on a 409 deactivation conflict', async () => {
  seed()
  mount()
  await screen.findByText('Haircut')
  fireEvent.click(screen.getByRole('button', { name: 'Deactivate Haircut' }))
  fetch.mockResolvedValueOnce(response(409))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm deactivation' }))
  expect(await screen.findByText('The item or commission rule changed. Refresh and try again.')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Deactivate Haircut' })).toBeTruthy()
  expect(screen.getByRole('dialog', { name: 'Deactivate service?' }).open).toBe(true)
})

it.each([403, 404, 409, 422, 500])('keeps the edit dialog open after HTTP %i', async (status) => {
  seed()
  mount()
  await screen.findByText('Haircut')
  fireEvent.click(screen.getByRole('button', { name: 'Edit Haircut' }))
  change('Name', 'Renamed')
  fetch.mockResolvedValueOnce(response(status))
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(screen.getByRole('dialog', { name: 'Edit Service' }).open).toBe(true))
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(screen.getByText('Haircut')).toBeTruthy()
})

it('offers retry after a network failure', async () => {
  fetch.mockRejectedValueOnce(new TypeError('offline'))
    .mockResolvedValueOnce(response(200, products)).mockResolvedValueOnce(response(200, rules))
  mount()
  expect(await screen.findByText('Catalog is temporarily unavailable. Please try again.')).toBeTruthy()
  seed()
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByText('Haircut')).toBeTruthy()
})
