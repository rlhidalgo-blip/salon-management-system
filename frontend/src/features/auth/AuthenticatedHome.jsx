import { useRef, useState } from 'react'
import StaffManagement from '../staff/StaffManagement.jsx'

import './AuthenticatedHome.css'

export default function AuthenticatedHome({ user, theme, csrfToken, onRevalidateSession, onToggleTheme, onLogout }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const submitting = useRef(false)

  async function handleLogout() {
    if (submitting.current) return
    submitting.current = true
    setLoading(true)
    setError('')
    try {
      await onLogout()
    } catch {
      setError('Could not sign out right now. Please try again.')
    } finally {
      submitting.current = false
      setLoading(false)
    }
  }

  if (user.role === 'Owner') {
    return (
      <div className="owner-app">
        <header className="owner-header">
          <div className="owner-header-inner">
            <img className="owner-logo" src="/assets/yabs-logo.png"
              alt="Yab's Hair and Beauty Studio" />
            <div className="owner-header-controls">
              <span className="owner-role">Role: {user.role}</span>
              <button className="landing-theme-toggle" type="button" onClick={onToggleTheme}
                aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}>
                {theme === 'light' ? 'Dark mode' : 'Light mode'}
              </button>
              <button className="owner-logout" type="button" onClick={handleLogout}
                disabled={loading} aria-busy={loading}>
                {loading ? 'Signing out…' : 'Logout'}
              </button>
            </div>
          </div>
        </header>
        <main className="owner-main">
          {error && <p className="owner-message" role="alert">{error}</p>}
          <StaffManagement csrfToken={csrfToken} onRevalidateSession={onRevalidateSession} />
        </main>
      </div>
    )
  }

  return (
    <main className="authenticated-home">
      <div className="authenticated-toolbar">
        <button className="landing-theme-toggle" type="button" onClick={onToggleTheme}
          aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}>
          {theme === 'light' ? 'Dark mode' : 'Light mode'}
        </button>
      </div>
      <section className="authenticated-content" aria-labelledby="authenticated-heading">
        <h1 id="authenticated-heading">Signed in</h1>
        <p>Username: {user.username}</p>
        <p>Role: {user.role}</p>
        <button className="landing-logout" type="button" onClick={handleLogout}
          disabled={loading} aria-busy={loading}>
          {loading ? 'Signing out…' : 'Logout'}
        </button>
        <p className="landing-message" role="alert">{error}</p>
      </section>
    </main>
  )
}
