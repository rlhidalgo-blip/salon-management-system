import { useRef, useState } from 'react'

import './AuthenticatedHome.css'

export default function AuthenticatedHome({ user, theme, onToggleTheme, onLogout }) {
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
