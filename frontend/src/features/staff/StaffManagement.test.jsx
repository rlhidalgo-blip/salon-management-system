// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import StaffManagement from './StaffManagement.jsx'

const rows = [
  { id: 8, name: 'Zoe', role: 'Stylist', active: false },
  { id: 2, name: 'Ana', role: 'Barber', active: true },
]
const reply = (status, body = null) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
const pending = () => {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}
const mount = (onRevalidateSession = vi.fn()) => render(
  <StaffManagement csrfToken="synthetic-csrf" onRevalidateSession={onRevalidateSession} />,
)

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
  HTMLDialogElement.prototype.showModal = function () { this.open = true }
  HTMLDialogElement.prototype.close = function () { this.open = false }
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('Owner staff management', () => {
  it('loads by ID and filters names and status without another request', async () => {
    fetch.mockResolvedValueOnce(reply(200, rows))
    mount()
    expect(await screen.findByText('Ana')).toBeTruthy()
    const names = [...document.querySelectorAll('.staff-table tbody tr td:first-child')].map((cell) => cell.textContent)
    expect(names).toEqual(['Ana', 'Zoe'])
    fireEvent.change(screen.getByLabelText('Search by name'), { target: { value: 'zo' } })
    expect(screen.queryByText('Ana')).toBeNull()
    expect(screen.getByText('Zoe')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'active' } })
    expect(screen.getByText('No staff match your search or filter.')).toBeTruthy()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('validates, creates with CSRF, and prevents duplicate submits', async () => {
    const response = pending()
    fetch.mockResolvedValueOnce(reply(200, [])).mockImplementationOnce(() => response.promise)
    mount()
    await screen.findByText('No staff members yet.')
    fireEvent.click(screen.getByRole('button', { name: 'Add Staff' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByText('Enter a staff name.')).toBeTruthy()
    expect(screen.getByText('Select a role.')).toBeTruthy()
    expect(fetch).toHaveBeenCalledTimes(1)
    fireEvent.change(screen.getByLabelText('Staff Name'), { target: { value: '  Bea  ' } })
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'Stylist' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    fireEvent.submit(screen.getByRole('button', { name: 'Saving…' }).closest('form'))
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(fetch.mock.calls[1]).toEqual(['/api/v1/staff', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'synthetic-csrf' },
      body: JSON.stringify({ name: 'Bea', role: 'Stylist' }),
    }])
    response.resolve(reply(201, { id: 9, name: 'Bea', role: 'Stylist', active: true }))
    expect(await screen.findByText('Bea')).toBeTruthy()
  })

  it('requires confirmation before deactivation and allows cancel', async () => {
    fetch.mockResolvedValueOnce(reply(200, rows))
      .mockResolvedValueOnce(reply(200, { ...rows[1], active: false }))
    mount()
    await screen.findByText('Ana')
    fireEvent.click(screen.getByRole('button', { name: 'Deactivate' }))
    expect(screen.getByText('Deactivate Ana? This keeps their historical records.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(fetch).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Deactivate' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm deactivation' }))
    await screen.findByText('Ana deactivated.')
    expect(fetch.mock.calls[1]).toEqual(['/api/v1/staff/2/status', {
      method: 'PATCH', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'synthetic-csrf' },
      body: JSON.stringify({ active: false }),
    }])
  })

  it('reactivates directly without confirmation', async () => {
    fetch.mockResolvedValueOnce(reply(200, rows))
      .mockResolvedValueOnce(reply(200, { ...rows[0], active: true }))
    mount()
    await screen.findByText('Zoe')
    fireEvent.click(screen.getByRole('button', { name: 'Activate' }))
    expect(await screen.findByText('Zoe activated.')).toBeTruthy()
    expect(fetch.mock.calls[1][0]).toBe('/api/v1/staff/8/status')
    expect(document.querySelector('dialog[aria-labelledby="deactivate-heading"]').open).toBe(false)
  })

  it('treats 403 as a permission error and 422 as validation feedback', async () => {
    fetch.mockResolvedValueOnce(reply(403))
    const { unmount } = mount()
    expect(await screen.findByText('You do not have permission to manage staff.')).toBeTruthy()
    expect(screen.queryByText('No staff members yet.')).toBeNull()
    unmount()
    fetch.mockResolvedValueOnce(reply(200, [])).mockResolvedValueOnce(reply(422))
    mount()
    await screen.findByText('No staff members yet.')
    fireEvent.click(screen.getByRole('button', { name: 'Add Staff' }))
    fireEvent.change(screen.getByLabelText('Staff Name'), { target: { value: 'Bea' } })
    fireEvent.change(screen.getByLabelText('Role'), { target: { value: 'Stylist' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Please check the staff information and try again.')).toBeTruthy()
  })

  it('revalidates on 401 and offers retry on network failure', async () => {
    const revalidate = vi.fn().mockResolvedValue(false)
    fetch.mockResolvedValueOnce(reply(401))
    const { unmount } = mount(revalidate)
    await waitFor(() => expect(revalidate).toHaveBeenCalledTimes(1))
    unmount()
    fetch.mockRejectedValueOnce(new TypeError('offline')).mockResolvedValueOnce(reply(200, rows))
    mount()
    expect(await screen.findByText('Staff Management is temporarily unavailable. Please try again.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Ana')).toBeTruthy()
  })
})
