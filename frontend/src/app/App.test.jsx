// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import App from './App.jsx'

vi.mock('../features/staff/StaffManagement.jsx', () => ({
  default: () => <section aria-label="Staff Management" />,
}))

const current = {
  user: { id: 1, username: 'synthetic_owner', role: 'Owner' },
  csrf_token: 'synthetic-csrf',
}

function reply(status, body = null) {
  return { ok: status >= 200 && status < 300, status, json: async () => body }
}

function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

function enterCredentials() {
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'synthetic_owner' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'synthetic-password' } })
}

beforeEach(() => {
  window.localStorage.clear()
  vi.stubGlobal('matchMedia', vi.fn(() => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })))
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('browser authentication flow', () => {
  it('shows staff controls only for an authenticated Owner', async () => {
    fetch.mockResolvedValueOnce(reply(200, current))
    const { unmount } = render(<App />)
    expect(await screen.findByRole('region', { name: 'Staff Management' })).toBeTruthy()
    unmount()
    fetch.mockResolvedValueOnce(reply(200, {
      ...current, user: { ...current.user, role: 'Cashier' },
    }))
    render(<App />)
    expect(await screen.findByText('Cashier')).toBeTruthy()
    expect(screen.queryByRole('region', { name: 'Staff Management' })).toBeNull()
  })
  it('verifies /me after login before showing the landing screen', async () => {
    const verification = deferred()
    fetch.mockResolvedValueOnce(reply(401))
      .mockResolvedValueOnce(reply(200, current))
      .mockImplementationOnce(() => verification.promise)
    render(<App />)
    await screen.findByRole('button', { name: 'Sign In' })
    enterCredentials()
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }))
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3))
    expect(screen.queryByText('Role: Owner')).toBeNull()
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/auth/me', '/api/v1/auth/login', '/api/v1/auth/me',
    ])
    expect(fetch.mock.calls[1][1]).toMatchObject({ method: 'POST', credentials: 'same-origin' })
    expect(fetch.mock.calls[2][1].credentials).toBe('same-origin')
    verification.resolve(reply(200, current))
    expect(await screen.findByText('Role: Owner')).toBeTruthy()
    expect(screen.getByRole('img', { name: "Yab's Hair and Beauty Studio" }).getAttribute('src'))
      .toBe('/assets/yabs-logo.png')
    expect(screen.queryByRole('heading', { name: 'Signed in' })).toBeNull()
  })

  it('shows generic invalid-credential feedback', async () => {
    fetch.mockResolvedValueOnce(reply(401)).mockResolvedValueOnce(reply(401))
    render(<App />)
    await screen.findByRole('button', { name: 'Sign In' })
    enterCredentials()
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }))
    expect(await screen.findByRole('alert')).toHaveProperty(
      'textContent', 'Unable to sign in. Check your credentials and try again.',
    )
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('restores a session on reload without flashing the login form', async () => {
    const verification = deferred()
    fetch.mockImplementationOnce(() => verification.promise)
    render(<App />)
    expect(screen.getByText('Checking your session…')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Sign In' })).toBeNull()
    verification.resolve(reply(200, current))
    expect(await screen.findByText('Role: Owner')).toBeTruthy()
  })

  it('treats an expired session as unauthenticated', async () => {
    fetch.mockResolvedValueOnce(reply(401))
    render(<App />)
    expect(await screen.findByRole('button', { name: 'Sign In' })).toBeTruthy()
    expect(screen.queryByText('Role: Owner')).toBeNull()
  })

  it('shows rate limiting without exposing account details', async () => {
    fetch.mockResolvedValueOnce(reply(401)).mockResolvedValueOnce(reply(429))
    render(<App />)
    await screen.findByRole('button', { name: 'Sign In' })
    enterCredentials()
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }))
    expect(await screen.findByText('Too many sign-in attempts. Please try again later.')).toBeTruthy()
  })

  it('retries a failed initial session check', async () => {
    fetch.mockRejectedValueOnce(new TypeError('network unavailable'))
      .mockResolvedValueOnce(reply(200, current))
    render(<App />)
    expect(await screen.findByRole('button', { name: 'Try again' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Sign In' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Role: Owner')).toBeTruthy()
  })

  it('allows retry after a temporary login failure', async () => {
    fetch.mockResolvedValueOnce(reply(401))
      .mockRejectedValueOnce(new TypeError('network unavailable'))
      .mockResolvedValueOnce(reply(200, current))
      .mockResolvedValueOnce(reply(200, current))
    render(<App />)
    await screen.findByRole('button', { name: 'Sign In' })
    enterCredentials()
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }))
    expect(await screen.findByText('Sign-in is temporarily unavailable. Please try again.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }))
    expect(await screen.findByText('Role: Owner')).toBeTruthy()
  })

  it('sends the in-memory CSRF token on logout and returns to login on 204', async () => {
    fetch.mockResolvedValueOnce(reply(200, current)).mockResolvedValueOnce(reply(204))
    render(<App />)
    await screen.findByText('Role: Owner')
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }))
    await screen.findByRole('button', { name: 'Sign In' })
    expect(fetch.mock.calls[1]).toEqual([
      '/api/v1/auth/logout',
      { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': 'synthetic-csrf' } },
    ])
    expect(window.localStorage.getItem('synthetic-csrf')).toBeNull()
  })

  it('keeps authenticated state after failed logout and allows retry', async () => {
    fetch.mockResolvedValueOnce(reply(200, current))
      .mockRejectedValueOnce(new TypeError('network unavailable'))
      .mockResolvedValueOnce(reply(204))
    render(<App />)
    await screen.findByText('Role: Owner')
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }))
    expect(await screen.findByText('Could not sign out right now. Please try again.')).toBeTruthy()
    expect(screen.getByText('Role: Owner')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }))
    expect(await screen.findByRole('button', { name: 'Sign In' })).toBeTruthy()
  })

  it('clears the UI only when logout confirms the session is invalid', async () => {
    fetch.mockResolvedValueOnce(reply(200, current)).mockResolvedValueOnce(reply(401))
    render(<App />)
    await screen.findByText('Role: Owner')
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }))
    expect(await screen.findByRole('button', { name: 'Sign In' })).toBeTruthy()
  })

  it('keeps required validation and password visibility controls', async () => {
    fetch.mockResolvedValueOnce(reply(401))
    render(<App />)
    await screen.findByRole('button', { name: 'Sign In' })
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }))
    expect(screen.getByText('Enter your username.')).toBeTruthy()
    expect(screen.getByText('Enter your password.')).toBeTruthy()
    expect(fetch).toHaveBeenCalledTimes(1)
    enterCredentials()
    expect(screen.getByLabelText('Password').type).toBe('password')
    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(screen.getByLabelText('Password').type).toBe('text')
  })

  it('retries /me rather than creating another session after post-login verification fails', async () => {
    fetch.mockResolvedValueOnce(reply(401))
      .mockResolvedValueOnce(reply(200, current))
      .mockRejectedValueOnce(new TypeError('network unavailable'))
      .mockResolvedValueOnce(reply(200, current))
    render(<App />)
    await screen.findByRole('button', { name: 'Sign In' })
    enterCredentials()
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Role: Owner')).toBeTruthy()
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/auth/me', '/api/v1/auth/login', '/api/v1/auth/me', '/api/v1/auth/me',
    ])
  })

  it('prevents duplicate login submissions while a request is pending', async () => {
    const pending = deferred()
    fetch.mockResolvedValueOnce(reply(401))
      .mockImplementationOnce(() => pending.promise)
      .mockResolvedValueOnce(reply(200, current))
    render(<App />)
    await screen.findByRole('button', { name: 'Sign In' })
    enterCredentials()
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }))
    fireEvent.submit(screen.getByRole('button', { name: 'Preparing…' }).closest('form'))
    expect(fetch).toHaveBeenCalledTimes(2)
    pending.resolve(reply(200, current))
    expect(await screen.findByText('Role: Owner')).toBeTruthy()
    expect(fetch).toHaveBeenCalledTimes(3)
  })
})
