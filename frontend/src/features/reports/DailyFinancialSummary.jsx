import { useEffect, useState } from 'react'

import { getDailyReport } from './dailyReportApi.js'
import './DailyFinancialSummary.css'

const manilaDay = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit', day: '2-digit',
})
const readableDate = new Intl.DateTimeFormat('en-US', {
  timeZone: 'UTC', year: 'numeric', month: 'long', day: 'numeric',
})

function todayInManila() {
  return manilaDay.format(new Date())
}

function displayDate(value) {
  return readableDate.format(new Date(`${value}T00:00:00Z`))
}

function peso(value) {
  // Backend Decimal strings are display-only here; never perform financial math in JS.
  const match = String(value).match(/^(\-?)(\d+)(?:\.(\d{1,2}))?$/)
  if (!match) return '—'
  const grouped = match[2].replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `₱${match[1]}${grouped}.${(match[3] || '').padEnd(2, '0')}`
}

function errorMessage(error) {
  if (error.status === 403) return 'You do not have permission to view this report date.'
  if (error.status === 422) return 'Choose a valid current or historical business date.'
  return 'Daily report is temporarily unavailable. Please try again.'
}

function MoneyLine({ label, value }) {
  return <div><dt>{label}</dt><dd>{peso(value)}</dd></div>
}

export default function DailyFinancialSummary({ user, onRevalidateSession }) {
  const owner = user.role === 'Owner'
  const [businessDate, setBusinessDate] = useState('')
  const [reload, setReload] = useState(0)
  const [result, setResult] = useState({ key: '', state: 'loading', report: null, error: '' })
  const key = `${businessDate}|${reload}`
  const current = result.key === key ? result : { state: 'loading', report: null, error: '' }

  useEffect(() => {
    const controller = new AbortController()
    setResult({ key, state: 'loading', report: null, error: '' })
    getDailyReport(owner ? businessDate : '', controller.signal).then((report) => {
      if (!controller.signal.aborted) setResult({ key, state: 'ready', report, error: '' })
    }).catch(async (error) => {
      if (controller.signal.aborted) return
      if (error.status === 401) {
        try { if (!await onRevalidateSession()) return } catch { /* Keep retry available. */ }
      }
      if (!controller.signal.aborted) setResult({ key, state: 'error', report: null,
        error: errorMessage(error) })
    })
    return () => controller.abort()
  }, [businessDate, key, owner, onRevalidateSession])

  useEffect(() => {
    let observedDay = todayInManila()
    const checkDay = () => {
      const day = todayInManila()
      if (day === observedDay) return
      observedDay = day
      // A blank date always means server-defined Manila today. Refresh its data
      // when the local day changes; server date/authorization remain authoritative.
      if (!owner || businessDate === '') setReload((count) => count + 1)
    }
    const interval = setInterval(checkDay, 30_000)
    window.addEventListener('focus', checkDay)
    document.addEventListener('visibilitychange', checkDay)
    return () => {
      clearInterval(interval)
      window.removeEventListener('focus', checkDay)
      document.removeEventListener('visibilitychange', checkDay)
    }
  }, [owner, businessDate])

  return <section className="daily-report" aria-labelledby="daily-report-title">
    <div className="daily-report-heading">
      <div>
        <h1 id="daily-report-title">Daily Financial Summary</h1>
        {current.state === 'ready' && <p className="daily-report-date">
          {displayDate(current.report.business_date)}
        </p>}
      </div>
      <div className="daily-report-controls">
        {owner && <label>Business date
          <input type="date" value={businessDate} max={todayInManila()}
            onChange={(event) => setBusinessDate(event.target.value)} />
        </label>}
        <button className="daily-report-refresh" type="button" aria-label="Refresh report"
          aria-busy={current.state === 'loading'} disabled={current.state === 'loading'}
          onClick={() => setReload((count) => count + 1)}>
          <svg data-icon="refresh" aria-hidden="true" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
            <path d="M21 3v5h-5" />
            <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
            <path d="M8 16H3v5" />
          </svg>
        </button>
      </div>
    </div>
    {current.state === 'loading' && <p className="daily-report-notice" role="status">Loading daily report…</p>}
    {current.state === 'error' && <div className="daily-report-error" role="alert">
      <p>{current.error}</p>
      <button type="button" onClick={() => setReload((count) => count + 1)}>Try again</button>
    </div>}
    {current.state === 'ready' && <div className="daily-report-body">
      <dl className="daily-report-totals">
        <MoneyLine label="Gross Sales" value={current.report.gross_sales} />
        <MoneyLine label="Staff Commission" value={current.report.total_staff_commission} />
        <MoneyLine label="Business Share" value={current.report.total_business_share} />
      </dl>
      <section className="daily-report-surface daily-report-payment" aria-labelledby="daily-payment-title">
        <h2 id="daily-payment-title">Payment Breakdown</h2>
        <dl>
          <MoneyLine label="Cash Sales" value={current.report.cash_sales} />
          <MoneyLine label="GCash Sales" value={current.report.gcash_sales} />
        </dl>
      </section>
      <section className="daily-report-surface daily-report-staff" aria-labelledby="daily-staff-title">
        <h2 id="daily-staff-title">Staff Commissions</h2>
        {current.report.staff_commissions.length === 0
          ? <p className="daily-report-empty">No staff commissions for this date.</p>
          : <ul>{current.report.staff_commissions.map((row) => <li key={row.staff_id}>
            <span>{row.current_staff_name}</span>
            <strong>{peso(row.total_staff_commission)}</strong>
          </li>)}</ul>}
      </section>
      {current.report.completed_transaction_count === 0 &&
        <p className="daily-report-notice">No completed sales for this date. Financial totals are zero.</p>}
    </div>}
  </section>
}
