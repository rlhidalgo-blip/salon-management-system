// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import CommissionRulesManagement from './CommissionRulesManagement.jsx'

const rows = [
  { id: 8, name: 'Product credit', type: 'Fixed', value: '25.50', active: false },
  { id: 2, name: 'Haircut', type: 'Percentage', value: '50.00', active: true },
]
const reply = (status, body = null) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}
const mount = (onRevalidateSession = vi.fn()) => render(
  <CommissionRulesManagement csrfToken="synthetic-csrf" onRevalidateSession={onRevalidateSession} />,
)
const change = (label, value) => fireEvent.change(screen.getByLabelText(label), { target: { value } })

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
  HTMLDialogElement.prototype.showModal = function () { this.open = true }
  HTMLDialogElement.prototype.close = function () { this.open = false }
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('Owner Commission Rules management', () => {
  it('lists both statuses by ID with safe string formatting and mobile labels', async () => {
    fetch.mockResolvedValueOnce(reply(200, rows))
    mount()
    await screen.findByText('Haircut')
    expect([...document.querySelectorAll('.commission-table tbody tr td:first-child')].map((cell) => cell.textContent))
      .toEqual(['Haircut', 'Product credit'])
    expect(screen.getByText('50%')).toBeTruthy()
    expect(screen.getByText('₱25.50')).toBeTruthy()
    expect(document.querySelectorAll('.commission-table thead th')).toHaveLength(5)
    expect(document.querySelector('.commission-table tbody td[data-label="Value"]')).toBeTruthy()
    expect(fetch.mock.calls[0]).toEqual(['/api/v1/commission-rules', { credentials: 'same-origin', signal: expect.any(AbortSignal) }])
  })

  it('shows an intentional empty state', async () => {
    fetch.mockResolvedValueOnce(reply(200, []))
    mount()
    expect(await screen.findByText('No commission rules yet.')).toBeTruthy()
    expect(document.querySelector('.commission-results .commission-empty')).toBeTruthy()
  })

  it('validates required fields and sends one decimal-string creation with CSRF', async () => {
    const pending = deferred()
    fetch.mockResolvedValueOnce(reply(200, [])).mockImplementationOnce(() => pending.promise)
    mount()
    await screen.findByText('No commission rules yet.')
    fireEvent.click(screen.getByRole('button', { name: 'Add Rule' }))
    expect(document.querySelector('dialog[aria-labelledby="add-rule-heading"]').open).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByText('Enter a rule name.')).toBeTruthy()
    expect(screen.getByText('Select a type.')).toBeTruthy()
    expect(screen.getByText('Enter a positive value with at most two decimal places.')).toBeTruthy()
    expect(fetch).toHaveBeenCalledTimes(1)
    change('Rule Name', '  Product credit  ')
    change('Type', 'Fixed')
    change('Value', '25.50')
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    fireEvent.submit(screen.getByRole('button', { name: 'Saving…' }).closest('form'))
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(fetch.mock.calls[1]).toEqual(['/api/v1/commission-rules', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'synthetic-csrf' },
      body: JSON.stringify({ name: 'Product credit', type: 'Fixed', value: '25.50' }),
    }])
    pending.resolve(reply(201, rows[0]))
    expect(await screen.findByText('Product credit')).toBeTruthy()
    expect(window.localStorage.getItem('synthetic-csrf')).toBeNull()
  })

  it.each([
    ['0', 'Fixed'], ['-1', 'Fixed'], ['1.001', 'Fixed'], ['abc', 'Fixed'],
    ['100.01', 'Percentage'], ['10000000000', 'Fixed'],
  ])('rejects invalid value %s for %s before requesting', async (value, type) => {
    fetch.mockResolvedValueOnce(reply(200, []))
    mount()
    await screen.findByText('No commission rules yet.')
    fireEvent.click(screen.getByRole('button', { name: 'Add Rule' }))
    change('Rule Name', 'Sample')
    change('Type', type)
    change('Value', value)
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByLabelText('Value').getAttribute('aria-invalid')).toBe('true')
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('allows cancel, then requires deactivation confirmation and shows 409 without changing status', async () => {
    fetch.mockResolvedValueOnce(reply(200, rows)).mockResolvedValueOnce(reply(409))
      .mockResolvedValueOnce(reply(200, { ...rows[1], active: false }))
    mount()
    await screen.findByText('Haircut')
    fireEvent.click(screen.getByRole('button', { name: 'Deactivate Haircut' }))
    expect(screen.getByText('Deactivate Haircut? This will not change historical commission snapshots.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(fetch).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Deactivate Haircut' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm deactivation' }))
    expect(await screen.findByText('Cannot deactivate: an active Service or Product still references this rule.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Deactivate Haircut' })).toBeTruthy()
    expect(document.querySelector('dialog[aria-labelledby="deactivate-rule-heading"]').open).toBe(true)
    expect(fetch.mock.calls[1]).toEqual(['/api/v1/commission-rules/2/status', {
      method: 'PATCH', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'synthetic-csrf' },
      body: JSON.stringify({ active: false }),
    }])
    fireEvent.click(screen.getByRole('button', { name: 'Confirm deactivation' }))
    expect(await screen.findByText('Haircut deactivated.')).toBeTruthy()
  })

  it('reactivates directly with CSRF', async () => {
    fetch.mockResolvedValueOnce(reply(200, rows)).mockResolvedValueOnce(reply(200, { ...rows[0], active: true }))
    mount()
    await screen.findByText('Product credit')
    fireEvent.click(screen.getByRole('button', { name: 'Activate Product credit' }))
    expect(await screen.findByText('Product credit activated.')).toBeTruthy()
    expect(fetch.mock.calls[1][0]).toBe('/api/v1/commission-rules/8/status')
    expect(fetch.mock.calls[1][1].headers['X-CSRF-Token']).toBe('synthetic-csrf')
    expect(document.querySelector('dialog[aria-labelledby="deactivate-rule-heading"]').open).toBe(false)
  })

  it('separates forbidden, server validation, and retryable network errors', async () => {
    fetch.mockResolvedValueOnce(reply(403))
    const { unmount } = mount()
    expect(await screen.findByText('You do not have permission to manage commission rules.')).toBeTruthy()
    expect(screen.queryByText('No commission rules yet.')).toBeNull()
    unmount()
    fetch.mockRejectedValueOnce(new TypeError('offline')).mockResolvedValueOnce(reply(200, []))
    mount()
    expect(await screen.findByText('Commission Rules is temporarily unavailable. Please try again.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByText('No commission rules yet.')
    fetch.mockResolvedValueOnce(reply(422))
    fireEvent.click(screen.getByRole('button', { name: 'Add Rule' }))
    change('Rule Name', 'Valid')
    change('Type', 'Percentage')
    change('Value', '50')
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Please check the rule information and try again.')).toBeTruthy()
  })

  it('revalidates 401 and preserves a retry path for temporary /me failure', async () => {
    const revalidate = vi.fn().mockResolvedValue(false)
    fetch.mockResolvedValueOnce(reply(401))
    const { unmount } = mount(revalidate)
    await waitFor(() => expect(revalidate).toHaveBeenCalledTimes(1))
    unmount()
    fetch.mockResolvedValueOnce(reply(401))
    const failingRevalidate = vi.fn().mockRejectedValue(new TypeError('offline'))
    mount(failingRevalidate)
    expect(await screen.findByText('Commission Rules is temporarily unavailable. Please try again.')).toBeTruthy()
    expect(failingRevalidate).toHaveBeenCalledTimes(1)
  })
})
