import { useEffect, useState } from 'react'

import AuthenticatedHome from '../features/auth/AuthenticatedHome.jsx'
import { getCurrentUser, login, logout } from '../features/auth/authApi.js'
import LoginPage from '../features/auth/LoginPage.jsx'
import { useTheme } from './useTheme.js'

export default function App() {
  const [theme, toggleTheme] = useTheme()
  const [authState, setAuthState] = useState('checking')
  const [session, setSession] = useState(null)
  const [checkAttempt, setCheckAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getCurrentUser(controller.signal).then((current) => {
      if (controller.signal.aborted) return
      setSession(current)
      setAuthState('authenticated')
    }).catch((error) => {
      if (controller.signal.aborted) return
      setSession(null)
      setAuthState(error.status === 401 ? 'unauthenticated' : 'check-error')
    })
    return () => controller.abort()
  }, [checkAttempt])

  async function handleLogin(username, password) {
    await login(username, password)
    try {
      const current = await getCurrentUser()
      setSession(current)
      setAuthState('authenticated')
    } catch (error) {
      if (error.status !== 401) setAuthState('check-error')
      throw error
    }
  }

  async function handleLogout() {
    try {
      await logout(session.csrfToken)
    } catch (error) {
      if (error.status !== 401) throw error
      // A 401 confirms this session is no longer valid.
    }
    setSession(null)
    setAuthState('unauthenticated')
  }

  if (authState === 'checking') {
    return <main className="session-check" role="status">Checking your session…</main>
  }

  if (authState === 'check-error') {
    return (
      <main className="session-check">
        <p role="alert">Unable to check your session right now.</p>
        <button type="button" onClick={() => {
          setAuthState('checking')
          setCheckAttempt((attempt) => attempt + 1)
        }}>Try again</button>
      </main>
    )
  }

  if (authState === 'authenticated') {
    return <AuthenticatedHome user={session.user} theme={theme}
      onToggleTheme={toggleTheme} onLogout={handleLogout} />
  }

  return <LoginPage theme={theme} onToggleTheme={toggleTheme} onLogin={handleLogin} />
}
