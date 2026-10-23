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
  expect(screen.getByRole('button', { name: 'Staff' }).getAttribute('aria-pressed')).toBe('true')
  expect(screen.getByRole('button', { name: 'Catalog' }).getAttribute('aria-pressed')).toBe('false')
  expect(screen.queryByRole('heading', { name: 'Commission Rules' })).toBeNull()
  expect(document.querySelector('.staff-results .staff-table')).toBeTruthy()
  const themeButton = screen.getByRole('button', { name: 'Switch to dark mode' })
  expect(themeButton.querySelector('svg[data-icon="sun"][aria-hidden="true"]')).toBeTruthy()
  expect(themeButton.textContent).toBe('')
  fireEvent.click(themeButton)
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(window.localStorage.getItem('yabs-theme')).toBe('dark')
  expect(themeButton.getAttribute('aria-label')).toBe('Switch to light mode')
  expect(themeButton.querySelector('svg[data-icon="moon"][aria-hidden="true"]')).toBeTruthy()
  fireEvent.click(themeButton)
  expect(document.documentElement.dataset.theme).toBe('light')
  expect(themeButton.getAttribute('aria-label')).toBe('Switch to dark mode')
  expect(fetch.mock.calls.map(([url]) => url)).toEqual(['/api/v1/auth/me', '/api/v1/staff'])
})

it('switches Owner sections without another authentication check', async () => {
  fetch.mockImplementation((url) => Promise.resolve(
    url.endsWith('/me') ? response(200, owner)
      : url === '/api/v1/staff' ? response(200, [{ id: 1, name: 'Ana', role: 'Barber', active: true }])
        : response(200, [{ id: 2, name: 'Haircut', type: 'Percentage', value: '50.00', active: true }]),
  ))
  render(<App />)
  await screen.findByText('Ana')
  fireEvent.click(screen.getByRole('button', { name: 'Commission Rules' }))
  expect(await screen.findByText('Haircut')).toBeTruthy()
  expect(screen.queryByRole('heading', { name: 'Staff Management' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Commission Rules' }).getAttribute('aria-pressed')).toBe('true')
  fireEvent.click(screen.getByRole('button', { name: 'Staff' }))
  expect(await screen.findByText('Ana')).toBeTruthy()
  expect(screen.queryByRole('heading', { name: 'Commission Rules' })).toBeNull()
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/auth/me')).toHaveLength(1)
})

it('switches into Catalog and its tabs without another session check', async () => {
  fetch.mockImplementation((url) => Promise.resolve(response(200,
    url.endsWith('/me') ? owner
      : url === '/api/v1/staff' ? [{ id: 1, name: 'Ana', role: 'Barber', active: true }]
        : url === '/api/v1/services' ? [{ id: 3, name: 'Haircut', current_price: '100.00',
          allows_variable_price: false, commission_rule_id: 2, active: true }]
          : url === '/api/v1/products' ? []
            : [{ id: 2, name: 'Haircut split', type: 'Percentage', value: '50.00', active: true }],
  )))
  render(<App />)
  await screen.findByText('Ana')
  fireEvent.click(screen.getByRole('button', { name: 'Catalog' }))
  expect(await screen.findByRole('heading', { name: 'Catalog Management' })).toBeTruthy()
  expect(screen.getByText('Haircut')).toBeTruthy()
  expect(screen.queryByText('Staff Management')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Products' }))
  expect(screen.getByText('No products yet.')).toBeTruthy()
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/auth/me')).toHaveLength(1)
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

it('revalidates Catalog 401 and returns to login when the session is invalid', async () => {
  fetch.mockImplementation((url) => Promise.resolve(url.endsWith('/me')
    ? response(fetch.mock.calls.filter(([path]) => path === '/api/v1/auth/me').length === 1 ? 200 : 401, owner)
    : url === '/api/v1/staff' ? response(200, []) : response(401)))
  render(<App />)
  await screen.findByText('No staff members yet.')
  fireEvent.click(screen.getByRole('button', { name: 'Catalog' }))
  expect(await screen.findByRole('button', { name: 'Sign In' })).toBeTruthy()
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/auth/me')).toHaveLength(2)
})

it('shows Sales as the Cashier primary screen without Owner management requests', async () => {
  fetch.mockResolvedValueOnce(response(200, {
    ...owner, user: { ...owner.user, role: 'Cashier' },
  })).mockResolvedValueOnce(response(200, { staff: [], services: [], products: [] }))
  render(<App />)
  expect(await screen.findByText('Role: Cashier')).toBeTruthy()
  expect(await screen.findByRole('heading', { name: 'Sales Recording' })).toBeTruthy()
  expect(screen.queryByText('Staff Management')).toBeNull()
  expect(screen.queryByText('Catalog Management')).toBeNull()
  expect(screen.queryByRole('navigation', { name: 'Owner sections' })).toBeNull()
  expect(fetch.mock.calls.map(([url]) => url)).toEqual(['/api/v1/auth/me', '/api/v1/sales/options'])
})
