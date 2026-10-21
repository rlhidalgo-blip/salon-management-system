import { useEffect, useRef, useState } from 'react'

import './LoginPage.css'

export default function LoginPage({ theme, onToggleTheme }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [touched, setTouched] = useState({ username: false, password: false })
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const timer = useRef(null)

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const usernameMissing = !username.trim()
  const passwordMissing = !password
  const usernameError = touched.username && usernameMissing
  const passwordError = touched.password && passwordMissing

  function submit(event) {
    event.preventDefault()
    setTouched({ username: true, password: true })
    if (usernameMissing || passwordMissing || loading) return

    // UI-only feedback. Do not send credentials or imply authentication worked.
    setMessage('')
    setLoading(true)
    timer.current = window.setTimeout(() => {
      setLoading(false)
      setMessage('Live sign-in is not connected yet. No request was sent.')
    }, 400)
  }

  return (
    <main className="login-layout">
      <section className="login-panel" aria-labelledby="login-heading">
        <div className="login-toolbar">
          <button className="theme-toggle" type="button" onClick={onToggleTheme}
            aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}>
            {theme === 'light' ? 'Dark mode' : 'Light mode'}
          </button>
        </div>

        <div className="login-content">
          <img className="login-logo" src="/assets/yabs-logo.png"
            alt="Yab's Hair and Beauty Studio" />
          <h1 id="login-heading">Welcome back</h1>
          <p className="login-intro">Sign in with your staff account.</p>

          <form className="login-form" onSubmit={submit} noValidate>
            <div className="field">
              <label htmlFor="username">Username</label>
              <input id="username" name="username" type="text" autoComplete="username"
                value={username} aria-invalid={usernameError}
                aria-describedby={usernameError ? 'username-error' : undefined}
                onChange={(event) => { setUsername(event.target.value); setMessage('') }}
                onBlur={() => setTouched((current) => ({ ...current, username: true }))}
                disabled={loading} required />
              {usernameError && <p className="field-error" id="username-error" role="alert">Enter your username.</p>}
            </div>

            <div className="field">
              <label htmlFor="password">Password</label>
              <div className="password-control">
                <input id="password" name="password" type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password" value={password} aria-invalid={passwordError}
                  aria-describedby={passwordError ? 'password-error' : undefined}
                  onChange={(event) => { setPassword(event.target.value); setMessage('') }}
                  onBlur={() => setTouched((current) => ({ ...current, password: true }))}
                  disabled={loading} required />
                <button className="visibility-toggle" type="button" disabled={loading}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword} onClick={() => setShowPassword((current) => !current)}>
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
              {passwordError && <p className="field-error" id="password-error" role="alert">Enter your password.</p>}
            </div>

            <button className="sign-in" type="submit"
              disabled={loading} aria-busy={loading}>
              {loading ? 'Preparing…' : 'Sign In'}
            </button>
            <p className="form-message" role="status" aria-live="polite">{message}</p>
          </form>
        </div>

        <p className="staff-footer">For authorized staff only.</p>
      </section>
    </main>
  )
}
