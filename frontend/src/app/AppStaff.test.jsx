// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'

import App from './App.jsx'

const response = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
const owner = { user: { id: 1, username: 'synthetic_owner', role: 'Owner' }, csrf_token: 'synthetic-csrf' }

beforeEach(() => {
  window.localStorage.clear()
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
  const mockedFetch = vi.fn()
  const rawImplementation = mockedFetch.mockImplementation.bind(mockedFetch)
  mockedFetch.mockImplementation = (handler) => rawImplementation((url, options) =>
    url === '/api/v1/sales/capabilities' ? Promise.resolve(response(200, { protocol: 'legacy' }))
      : handler(url, options))
  vi.stubGlobal('fetch', mockedFetch)
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('opens the mobile Cashier drawer, restores focus on Escape, and closes after navigation', async () => {
  matchMedia.mockImplementation((query) => ({ matches: query.includes('1050px'), addEventListener: vi.fn(), removeEventListener: vi.fn() }))
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
  const cashier = { ...owner, user: { ...owner.user, role: 'Cashier' } }
  fetch.mockImplementation((url) => Promise.resolve(response(200,
    url.endsWith('/me') ? cashier : url.endsWith('/sales/options')
      ? { staff: [], services: [], products: [] } : { items: [], next_cursor: null })))
  render(<App />)
  await screen.findByRole('heading', { name: 'Sales Recording' })
  const menu = screen.getByRole('button', { name: 'Open menu' })
  expect(screen.queryByRole('button', { name: 'Staff' })).toBeNull()
  fireEvent.click(menu)
  const drawer = screen.getByRole('dialog', { name: 'Application navigation' })
  expect(document.activeElement).toBe(within(drawer).getByRole('button', { name: 'Close menu' }))
  fireEvent(drawer, new Event('cancel', { bubbles: true, cancelable: true }))
  expect(screen.queryByRole('dialog', { name: 'Application navigation' })).toBeNull()
  expect(document.activeElement).toBe(menu)
  fireEvent.click(menu)
  fireEvent.click(within(screen.getByRole('dialog', { name: 'Application navigation' }))
    .getByRole('button', { name: 'History' }))
  expect(await screen.findByRole('heading', { name: 'Transaction History' })).toBeTruthy()
  expect(screen.queryByRole('dialog', { name: 'Application navigation' })).toBeNull()
  expect(fetch.mock.calls.filter(([url]) => url.endsWith('/me'))).toHaveLength(1)
})

it.each([[1024, true], [1280, false]])('uses the appropriate shell at %ipx', async (width, drawer) => {
  matchMedia.mockImplementation((query) => ({ matches: query.includes('1050px') && width <= 1050,
    addEventListener: vi.fn(), removeEventListener: vi.fn() }))
  fetch.mockImplementation((url) => Promise.resolve(response(200, url.endsWith('/me') ? owner : [])))
  render(<App />)
  await screen.findByRole('heading', { name: 'Staff Management' })
  expect(Boolean(screen.queryByRole('button', { name: 'Open menu' }))).toBe(drawer)
  expect(Boolean(screen.queryByRole('complementary', { name: 'Application sidebar' }))).toBe(!drawer)
})

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
    .mockResolvedValueOnce(response(200, { protocol: 'legacy' }))
  render(<App />)
  expect(await screen.findByText('Role: Cashier')).toBeTruthy()
  expect(await screen.findByRole('heading', { name: 'Sales Recording' })).toBeTruthy()
  expect(screen.queryByText('Staff Management')).toBeNull()
  expect(screen.queryByText('Catalog Management')).toBeNull()
  expect(screen.queryByRole('navigation', { name: 'Owner sections' })).toBeNull()
  expect(fetch.mock.calls.map(([url]) => url)).toEqual(['/api/v1/auth/me',
    '/api/v1/sales/capabilities', '/api/v1/sales/options'])
})

it('adds Owner History without changing the default Staff section or rechecking the session', async () => {
  fetch.mockImplementation((url) => Promise.resolve(response(200,
    url.endsWith('/me') ? owner : url === '/api/v1/staff' ? []
      : { items: [], next_cursor: null })))
  render(<App />)
  await screen.findByRole('heading', { name: 'Staff Management' })
  expect(screen.getByRole('button', { name: 'Staff' }).getAttribute('aria-pressed')).toBe('true')
  fireEvent.click(screen.getByRole('button', { name: 'History' }))
  expect(await screen.findByRole('heading', { name: 'Transaction History' })).toBeTruthy()
  expect(screen.getByLabelText('Business date')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Staff' }))
  expect(await screen.findByRole('heading', { name: 'Staff Management' })).toBeTruthy()
  expect(fetch.mock.calls.filter(([url]) => url.endsWith('/me'))).toHaveLength(1)
})

it('keeps Cashier Sales primary and exposes only Sales and today-only History', async () => {
  const cashier = { ...owner, user: { ...owner.user, role: 'Cashier' } }
  fetch.mockImplementation((url) => Promise.resolve(response(200,
    url.endsWith('/me') ? cashier : url.endsWith('/sales/options')
      ? { staff: [], services: [], products: [] } : { items: [], next_cursor: null })))
  render(<App />)
  await screen.findByRole('heading', { name: 'Sales Recording' })
  const sections = screen.getByRole('navigation', { name: 'Cashier sections' })
  expect(within(sections).getAllByRole('button').map((button) => button.textContent)).toEqual(['Sales', 'History', 'Reports'])
  fireEvent.click(within(sections).getByRole('button', { name: 'History' }))
  expect(await screen.findByRole('heading', { name: 'Transaction History' })).toBeTruthy()
  expect(screen.queryByLabelText('Business date')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Staff' })).toBeNull()
  fireEvent.click(within(sections).getByRole('button', { name: 'Sales' }))
  expect(await screen.findByRole('heading', { name: 'Sales Recording' })).toBeTruthy()
  expect(fetch.mock.calls.filter(([url]) => url.endsWith('/me'))).toHaveLength(1)
})

const dailyReport = { business_date: '2026-10-23', gross_sales: '100.00', cash_sales: '100.00',
  gcash_sales: '0.00', total_staff_commission: '50.00', total_business_share: '50.00',
  completed_transaction_count: 1, voided_transaction_count: 0, staff_commissions: [] }
const monthlyReport = { reporting_month: '2026-10', gross_sales: '100.00', cash_sales: '100.00',
  gcash_sales: '0.00', total_staff_commission: '50.00', total_business_share: '50.00',
  completed_transaction_count: 1, voided_transaction_count: 0, staff_performance: [],
  unassigned_product_sales: '0.00' }

it('adds Owner Reports after History, preserves Staff default, and reloads on section return', async () => {
  fetch.mockImplementation((url) => Promise.resolve(response(200,
    url.endsWith('/me') ? owner : url === '/api/v1/staff' ? [] : dailyReport)))
  render(<App />)
  await screen.findByRole('heading', { name: 'Staff Management' })
  const sections = screen.getByRole('navigation', { name: 'Owner sections' })
  expect(within(sections).getAllByRole('button').map((button) => button.textContent)).toEqual([
    'Staff', 'Commission Rules', 'Catalog', 'Sales', 'History', 'Reports',
  ])
  fireEvent.click(within(sections).getByRole('button', { name: 'Reports' }))
  expect(await screen.findByRole('heading', { name: 'Daily Financial Summary' })).toBeTruthy()
  expect(screen.getByLabelText('Business date')).toBeTruthy()
  fireEvent.click(within(sections).getByRole('button', { name: 'Staff' }))
  await screen.findByRole('heading', { name: 'Staff Management' })
  fireEvent.click(within(sections).getByRole('button', { name: 'Reports' }))
  await waitFor(() => expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/reports/daily')).toHaveLength(2))
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/auth/me')).toHaveLength(1)
})

it('switches Owner Daily and Monthly reports without another session check', async () => {
  fetch.mockImplementation((url) => Promise.resolve(response(200,
    url.endsWith('/me') ? owner : url === '/api/v1/staff' ? []
      : url === '/api/v1/reports/monthly' ? monthlyReport : dailyReport)))
  render(<App />)
  await screen.findByRole('heading', { name: 'Staff Management' })
  fireEvent.click(screen.getByRole('button', { name: 'Reports' }))
  expect(await screen.findByRole('heading', { name: 'Daily Financial Summary' })).toBeTruthy()
  const views = screen.getByRole('navigation', { name: 'Report views' })
  expect(within(views).getByRole('button', { name: 'Daily' }).getAttribute('aria-pressed')).toBe('true')
  fireEvent.click(within(views).getByRole('button', { name: 'Monthly' }))
  expect(await screen.findByRole('heading', { name: 'Monthly Financial Summary' })).toBeTruthy()
  expect(screen.getByLabelText('Reporting month')).toBeTruthy()
  expect(screen.queryByRole('heading', { name: 'Daily Financial Summary' })).toBeNull()
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/reports/monthly')).toHaveLength(1)
  fireEvent.click(within(views).getByRole('button', { name: 'Daily' }))
  expect(await screen.findByRole('heading', { name: 'Daily Financial Summary' })).toBeTruthy()
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/auth/me')).toHaveLength(1)
})

it('adds today-only Reports for Cashier without Owner management controls', async () => {
  const cashier = { ...owner, user: { ...owner.user, role: 'Cashier' } }
  fetch.mockImplementation((url) => Promise.resolve(response(200,
    url.endsWith('/me') ? cashier : url.endsWith('/sales/options')
      ? { staff: [], services: [], products: [] } : dailyReport)))
  render(<App />)
  await screen.findByRole('heading', { name: 'Sales Recording' })
  const sections = screen.getByRole('navigation', { name: 'Cashier sections' })
  expect(within(sections).getAllByRole('button').map((button) => button.textContent)).toEqual(['Sales', 'History', 'Reports'])
  fireEvent.click(within(sections).getByRole('button', { name: 'Reports' }))
  expect(await screen.findByRole('heading', { name: 'Daily Financial Summary' })).toBeTruthy()
  expect(screen.queryByLabelText('Business date')).toBeNull()
  expect(screen.queryByRole('navigation', { name: 'Report views' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Staff' })).toBeNull()
  expect(fetch.mock.calls.some(([url]) => url.startsWith('/api/v1/reports/monthly'))).toBe(false)
  expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/auth/me')).toHaveLength(1)
})

it('revalidates a Reports 401 and returns to login when the session expired', async () => {
  const cashier = { ...owner, user: { ...owner.user, role: 'Cashier' } }
  let checks = 0
  fetch.mockImplementation((url) => Promise.resolve(url.endsWith('/me')
    ? response(++checks === 1 ? 200 : 401, cashier)
    : url.endsWith('/sales/options') ? response(200, { staff: [], services: [], products: [] })
      : response(401, {})))
  render(<App />)
  await screen.findByRole('heading', { name: 'Sales Recording' })
  fireEvent.click(screen.getByRole('button', { name: 'Reports' }))
  expect(await screen.findByRole('button', { name: 'Sign In' })).toBeTruthy()
  expect(checks).toBe(2)
})

it.each([320, 360, 390].flatMap((width) => ['Owner', 'Cashier'].map((role) => [width, role])))(
  'keeps header, theme, logout, and Reports controls functional at %ipx for %s', async (width, role) => {
    const priorWidth = window.innerWidth
    window.innerWidth = width
    matchMedia.mockImplementation((query) => ({ matches: query.includes('1050px'), addEventListener: vi.fn(), removeEventListener: vi.fn() }))
    HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
    HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
    try {
      const account = { ...owner, user: { ...owner.user, role } }
      fetch.mockImplementation((url) => Promise.resolve(url.endsWith('/me') ? response(200, account)
        : url === '/api/v1/staff' ? response(200, [])
          : url === '/api/v1/sales/options' ? response(200, { staff: [], services: [], products: [] })
            : url === '/api/v1/reports/daily' ? response(200, dailyReport)
              : url.endsWith('/logout') ? response(204) : response(404)))
      render(<App />)
      await screen.findByText(`Role: ${role}`)
      const header = screen.getByRole('banner')
      const logo = within(header).getByRole('img', { name: "Yab's Hair and Beauty Studio" })
      const toggle = within(header).getByRole('button', { name: 'Switch to dark mode' })
      const logout = within(header).getByRole('button', { name: 'Logout' })
      expect(logo).toBeTruthy()
      expect(toggle.parentElement).toBe(logout.parentElement)
      expect(toggle.nextElementSibling).toBe(logout)
      fireEvent.click(toggle)
      expect(document.documentElement.dataset.theme).toBe('dark')
      fireEvent.click(toggle)
      expect(document.documentElement.dataset.theme).toBe('light')
      fireEvent.click(within(header).getByRole('button', { name: 'Open menu' }))
      fireEvent.click(within(screen.getByRole('dialog', { name: 'Application navigation' }))
        .getByRole('button', { name: 'Reports' }))
      const refresh = await screen.findByRole('button', { name: 'Refresh report' })
      await waitFor(() => expect(refresh.disabled).toBe(false))
      fireEvent.click(refresh)
      await waitFor(() => expect(fetch.mock.calls.filter(([url]) => url === '/api/v1/reports/daily')).toHaveLength(2))
      fireEvent.click(logout)
      expect(await screen.findByRole('button', { name: 'Sign In' })).toBeTruthy()
    } finally {
      window.innerWidth = priorWidth
    }
  },
)

it('revalidates History 401 and returns to login when the Cashier session expired', async () => {
  const cashier = { ...owner, user: { ...owner.user, role: 'Cashier' } }
  let checks = 0
  fetch.mockImplementation((url) => Promise.resolve(url.endsWith('/me')
    ? response(++checks === 1 ? 200 : 401, cashier)
    : url.endsWith('/sales/options') ? response(200, { staff: [], services: [], products: [] })
      : response(401, {})))
  render(<App />)
  await screen.findByRole('heading', { name: 'Sales Recording' })
  fireEvent.click(screen.getByRole('button', { name: 'History' }))
  expect(await screen.findByRole('button', { name: 'Sign In' })).toBeTruthy()
  expect(checks).toBe(2)
})
