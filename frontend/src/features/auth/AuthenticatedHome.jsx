import { useRef, useState } from 'react'
import CommissionRulesManagement from '../commissions/CommissionRulesManagement.jsx'
import CatalogManagement from '../catalog/CatalogManagement.jsx'
import StaffManagement from '../staff/StaffManagement.jsx'
import SalesRecording from '../sales/SalesRecording.jsx'
import { usePendingSale } from '../sales/usePendingSale.js'
import TransactionHistory from '../transactions/TransactionHistory.jsx'
import ReportsSection from '../reports/ReportsSection.jsx'

import './AuthenticatedHome.css'

export default function AuthenticatedHome({ user, theme, csrfToken, onRevalidateSession, onToggleTheme, onLogout }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [ownerSection, setOwnerSection] = useState('staff')
  const [cashierSection, setCashierSection] = useState('sales')
  const submitting = useRef(false)
  const pendingSale = usePendingSale(user, onRevalidateSession)

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
              <button className="landing-theme-toggle owner-theme-toggle" type="button" onClick={onToggleTheme}
                aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}>
                {theme === 'light' ? (
                  <svg data-icon="sun" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                    <circle cx="12" cy="12" r="4" />
                    <path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" />
                  </svg>
                ) : (
                  <svg data-icon="moon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5a8.5 8.5 0 1 0 10.7 10.7Z" />
                  </svg>
                )}
              </button>
              <button className="owner-logout" type="button" onClick={handleLogout}
                disabled={loading} aria-busy={loading}>
                {loading ? 'Signing out…' : 'Logout'}
              </button>
            </div>
          </div>
        </header>
        <main className="owner-main">
          <nav className="owner-sections" aria-label="Owner sections">
            <button type="button" aria-pressed={ownerSection === 'staff'}
              onClick={() => setOwnerSection('staff')}>Staff</button>
            <button type="button" aria-pressed={ownerSection === 'commissions'}
              onClick={() => setOwnerSection('commissions')}>Commission Rules</button>
            <button type="button" aria-pressed={ownerSection === 'catalog'}
              onClick={() => setOwnerSection('catalog')}>Catalog</button>
            <button type="button" aria-pressed={ownerSection === 'sales'}
              onClick={() => setOwnerSection('sales')}>Sales</button>
            <button type="button" aria-pressed={ownerSection === 'history'}
              onClick={() => setOwnerSection('history')}>History</button>
            <button type="button" aria-pressed={ownerSection === 'reports'}
              onClick={() => setOwnerSection('reports')}>Reports</button>
          </nav>
          {error && <p className="owner-message" role="alert">{error}</p>}
          {ownerSection === 'staff'
            ? <StaffManagement csrfToken={csrfToken} onRevalidateSession={onRevalidateSession} />
            : ownerSection === 'commissions'
              ? <CommissionRulesManagement csrfToken={csrfToken} onRevalidateSession={onRevalidateSession} />
              : ownerSection === 'catalog'
                ? <CatalogManagement csrfToken={csrfToken} onRevalidateSession={onRevalidateSession} />
                : ownerSection === 'sales'
                  ? <SalesRecording user={user} csrfToken={csrfToken} onRevalidateSession={onRevalidateSession}
                      pendingSale={pendingSale} />
                  : ownerSection === 'history'
                    ? <TransactionHistory user={user} csrfToken={csrfToken}
                        onRevalidateSession={onRevalidateSession} />
                    : <ReportsSection user={user} onRevalidateSession={onRevalidateSession} />}
        </main>
      </div>
    )
  }

  return <div className="owner-app">
    <header className="owner-header"><div className="owner-header-inner">
      <img className="owner-logo" src="/assets/yabs-logo.png" alt="Yab's Hair and Beauty Studio" />
      <div className="owner-header-controls"><span className="owner-role">Role: {user.role}</span>
        <button className="landing-theme-toggle owner-theme-toggle" type="button" onClick={onToggleTheme}
          aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}>
          {theme === 'light' ? (
            <svg data-icon="sun" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" />
            </svg>
          ) : (
            <svg data-icon="moon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5a8.5 8.5 0 1 0 10.7 10.7Z" />
            </svg>
          )}
        </button>
        <button className="owner-logout" type="button" onClick={handleLogout} disabled={loading} aria-busy={loading}>
          {loading ? 'Signing out…' : 'Logout'}
        </button>
      </div>
    </div></header>
    <main className="owner-main">
      <nav className="owner-sections" aria-label="Cashier sections">
        <button type="button" aria-pressed={cashierSection === 'sales'}
          onClick={() => setCashierSection('sales')}>Sales</button>
        <button type="button" aria-pressed={cashierSection === 'history'}
          onClick={() => setCashierSection('history')}>History</button>
        <button type="button" aria-pressed={cashierSection === 'reports'}
          onClick={() => setCashierSection('reports')}>Reports</button>
      </nav>
      {error && <p className="owner-message" role="alert">{error}</p>}
      {cashierSection === 'sales'
        ? <SalesRecording user={user} csrfToken={csrfToken} onRevalidateSession={onRevalidateSession}
            pendingSale={pendingSale} />
        : cashierSection === 'history'
          ? <TransactionHistory user={user} csrfToken={csrfToken}
              onRevalidateSession={onRevalidateSession} />
          : <ReportsSection user={user} onRevalidateSession={onRevalidateSession} />}
    </main>
  </div>
}
