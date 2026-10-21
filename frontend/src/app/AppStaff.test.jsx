// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import App from './App.jsx'

const response = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
const owner = { user: { id: 1, username: 'synthetic_owner', role: 'Owner' }, csrf_token: 'synthetic-csrf' }

beforeEach(() => {
  window.localStorage.clear()
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('restores an Owner session and loads staff without flashing login', async () => {
  fetch.mockImplementation((url) => Promise.resolve(url.endsWith('/me')
    ? response(200, owner) : response(200, [{ id: 1, name: 'Ana', role: 'Barber', active: true }])))
  render(<App />)
  expect(screen.queryByRole('button', { name: 'Sign In' })).toBeNull()
  expect(await screen.findByText('Ana')).toBeTruthy()
  expect(screen.getByRole('banner')).toBeTruthy()
  expect(screen.getByText('Role: Owner')).toBeTruthy()
  expect(screen.getByRole('img', { name: "Yab's Hair and Beauty Studio" }).getAttribute('src'))
    .toBe('/assets/yabs-logo.png')
  expect(screen.queryByRole('heading', { name: 'Signed in' })).toBeNull()
  expect(screen.getByRole('heading', { name: 'Staff Management' })).toBeTruthy()
  expect(document.querySelector('.staff-results .staff-table')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Switch to dark mode' }))
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(window.localStorage.getItem('yabs-theme')).toBe('dark')
  expect(fetch.mock.calls.map(([url]) => url)).toEqual(['/api/v1/auth/me', '/api/v1/staff'])
})

it('revalidates staff 401 and returns to login when the session is invalid', async () => {
  fetch.mockResolvedValueOnce(response(200, owner))
    .mockResolvedValueOnce(response(401))
    .mockResolvedValueOnce(response(401))
  render(<App />)
  expect(await screen.findByRole('button', { name: 'Sign In' })).toBeTruthy()
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3))
  expect(fetch.mock.calls.map(([url]) => url)).toEqual([
    '/api/v1/auth/me', '/api/v1/staff', '/api/v1/auth/me',
  ])
})

it('keeps Cashier on the minimal landing screen without staff requests', async () => {
  fetch.mockResolvedValueOnce(response(200, {
    ...owner, user: { ...owner.user, role: 'Cashier' },
  }))
  render(<App />)
  expect(await screen.findByText('Role: Cashier')).toBeTruthy()
  expect(screen.getByRole('heading', { name: 'Signed in' })).toBeTruthy()
  expect(screen.queryByRole('banner')).toBeNull()
  expect(screen.queryByText('Staff Management')).toBeNull()
  expect(fetch).toHaveBeenCalledTimes(1)
})
