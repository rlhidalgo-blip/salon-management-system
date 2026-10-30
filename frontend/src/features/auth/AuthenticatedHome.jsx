import { useEffect, useRef, useState } from 'react'
import CommissionRulesManagement from '../commissions/CommissionRulesManagement.jsx'
import CatalogManagement from '../catalog/CatalogManagement.jsx'
import StaffManagement from '../staff/StaffManagement.jsx'
import SalesRecording from '../sales/SalesRecording.jsx'
import { usePendingSale } from '../sales/usePendingSale.js'
import TransactionHistory from '../transactions/TransactionHistory.jsx'
import ReportsSection from '../reports/ReportsSection.jsx'
import AppNavigation from './AppNavigation.jsx'
import './AuthenticatedHome.css'

const mediaQuery = '(max-width: 1050px)'
const narrowScreen = () => window.matchMedia(mediaQuery).matches

export default function AuthenticatedHome({ user, theme, csrfToken, onRevalidateSession, onToggleTheme, onLogout }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [section, setSection] = useState(user.role === 'Owner' ? 'staff' : 'sales')
  const [mobile, setMobile] = useState(narrowScreen)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [leaveTarget, setLeaveTarget] = useState(null)
  const [salesDraft, setSalesDraft] = useState(false)
  const submitting = useRef(false)
  const menuRef = useRef(null)
  const cancelRef = useRef(null)
  const leaveDialogRef = useRef(null)
  const leaveTriggerRef = useRef(null)
  const mainRef = useRef(null)
  const pendingSale = usePendingSale(user, onRevalidateSession)
  const allowed = user.role === 'Owner'
    ? ['staff', 'commissions', 'catalog', 'sales', 'history', 'reports']
    : ['sales', 'history', 'reports']
  const current = allowed.includes(section) ? section : allowed[0]
  const unresolved = pendingSale.blocked || Boolean(pendingSale.pending) || pendingSale.working

  useEffect(() => {
    const query = window.matchMedia(mediaQuery)
    const update = () => setMobile(query.matches)
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])
  useEffect(() => { if (!mobile) setDrawerOpen(false) }, [mobile])
  useEffect(() => {
    const dialog = leaveDialogRef.current
    if (leaveTarget) { dialog.showModal(); cancelRef.current?.focus() }
    else if (dialog.open) dialog.close()
    return () => { if (dialog.open) dialog.close() }
  }, [leaveTarget])

  function closeDrawer() {
    setDrawerOpen(false)
    menuRef.current?.focus()
  }
  function selectSection(next) {
    if (!allowed.includes(next) || next === current) return
    if (current === 'sales' && unresolved) {
      setError('Resolve the pending sale before leaving Sales.')
      return
    }
    if (current === 'sales' && salesDraft) {
      leaveTriggerRef.current = document.activeElement
      setLeaveTarget({ type: 'section', value: next })
      return
    }
    setSalesDraft(false)
    setError('')
    setSection(next)
  }
  async function handleLogout() {
    if (submitting.current) return
    submitting.current = true
    setLoading(true)
    setError('')
    try { await onLogout() }
    catch { setError('Could not sign out right now. Please try again.') }
    finally { submitting.current = false; setLoading(false) }
  }
  function requestLogout() {
    if (current === 'sales' && salesDraft && !unresolved) {
      leaveTriggerRef.current = document.activeElement
      setLeaveTarget({ type: 'logout' })
    }
    else handleLogout()
  }
  function cancelLeave() {
    leaveDialogRef.current?.close()
    setLeaveTarget(null)
    leaveTriggerRef.current?.focus()
  }
  function confirmLeave() {
    const target = leaveTarget
    leaveDialogRef.current?.close()
    setLeaveTarget(null)
    if (unresolved) {
      setError('Resolve the pending sale before leaving Sales.')
      return
    }
    if (target.type === 'logout') handleLogout()
    else { setSalesDraft(false); setError(''); setSection(target.value); mainRef.current?.focus() }
  }

  return <div className="owner-app">
    <AppNavigation role={user.role} section={current} onSelect={selectSection}
      mobile={mobile} open={drawerOpen} onClose={closeDrawer} />
    <div className="owner-content-area">
      <header className="owner-header"><div className="owner-header-inner">
        {mobile && <div className="owner-mobile-brand">
          <button ref={menuRef} className="owner-menu-button" type="button" onClick={() => setDrawerOpen(true)}
            aria-label="Open menu" aria-expanded={drawerOpen}>
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <path d="M4 7h16M4 12h16M4 17h16" />
            </svg>
          </button>
          <img className="owner-logo" src="/assets/yabs-logo.png" alt="Yab's Hair and Beauty Studio" />
        </div>}
        <div className="owner-header-controls">
          <span className="owner-role">{user.role === 'Cashier' ? 'Cashier' : `Role: ${user.role}`}</span>
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
          <button className="owner-logout" type="button" onClick={requestLogout} disabled={loading} aria-busy={loading}>
            {loading ? 'Signing out…' : 'Logout'}
          </button>
        </div>
      </div></header>
      <main ref={mainRef} tabIndex={-1} className="owner-main">
        {error && <p className="owner-message" role="alert">{error}</p>}
        {current === 'staff' ? <StaffManagement csrfToken={csrfToken} onRevalidateSession={onRevalidateSession} />
          : current === 'commissions' ? <CommissionRulesManagement csrfToken={csrfToken} onRevalidateSession={onRevalidateSession} />
            : current === 'catalog' ? <CatalogManagement csrfToken={csrfToken} onRevalidateSession={onRevalidateSession} />
              : current === 'sales' ? <SalesRecording user={user} csrfToken={csrfToken}
                  onRevalidateSession={onRevalidateSession} pendingSale={pendingSale} onDraftChange={setSalesDraft} />
                : current === 'history' ? <TransactionHistory user={user} csrfToken={csrfToken}
                    onRevalidateSession={onRevalidateSession} />
                  : <ReportsSection user={user} onRevalidateSession={onRevalidateSession} />}
      </main>
    </div>
    <dialog className="sales-leave-dialog" ref={leaveDialogRef} aria-labelledby="sales-leave-title"
      onCancel={(event) => { event.preventDefault(); cancelLeave() }}>
      <h2 id="sales-leave-title">Leave Sales?</h2>
      <p>Unsent Direct or Manual Sale details will be discarded. This cannot be undone.</p>
      <div className="sales-leave-actions">
        <button ref={cancelRef} type="button" onClick={cancelLeave}>Keep draft</button>
        <button type="button" onClick={confirmLeave}>Discard draft and leave</button>
      </div>
    </dialog>
  </div>
}
