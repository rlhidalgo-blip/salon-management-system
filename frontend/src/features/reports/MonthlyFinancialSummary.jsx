import { useEffect, useState } from 'react'

import { getMonthlyReport } from './monthlyReportApi.js'
import './MonthlyFinancialSummary.css'

const manilaMonth = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit',
})
const readableMonth = new Intl.DateTimeFormat('en-US', {
  timeZone: 'UTC', year: 'numeric', month: 'long',
})

function currentManilaMonth() {
  const parts = manilaMonth.formatToParts(new Date())
  const year = parts.find((part) => part.type === 'year').value
  const month = parts.find((part) => part.type === 'month').value
  return `${year}-${month}`
}

function displayMonth(value) {
  return readableMonth.format(new Date(`${value}-01T00:00:00Z`))
}

function peso(value) {
  // Decimal response strings are display-only; no financial arithmetic in JavaScript.
  const match = String(value).match(/^(-?)(\d+)(?:\.(\d{1,2}))?$/)
  if (!match) return '—'
  const grouped = match[2].replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `₱${match[1]}${grouped}.${(match[3] || '').padEnd(2, '0')}`
}

function errorMessage(error) {
  if (error.status === 403) return 'You do not have permission to view monthly reports.'
  if (error.status === 422) return 'Choose a valid current or historical month.'
  return 'Monthly report is temporarily unavailable. Please try again.'
}

function MoneyLine({ label, value }) {
  return <div><dt>{label}</dt><dd>{peso(value)}</dd></div>
}

export default function MonthlyFinancialSummary({ onRevalidateSession }) {
  const [month, setMonth] = useState('')
  const [latestMonth, setLatestMonth] = useState(currentManilaMonth)
  const [reload, setReload] = useState(0)
  const [result, setResult] = useState({ key: '', state: 'loading', report: null, error: '' })
  const key = `${month}|${reload}`
  const current = result.key === key ? result : { state: 'loading', report: null, error: '' }

  useEffect(() => {
    const controller = new AbortController()
    setResult({ key, state: 'loading', report: null, error: '' })
    getMonthlyReport(month, controller.signal).then((report) => {
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
  }, [key, month, onRevalidateSession])

  useEffect(() => {
    let observedMonth = currentManilaMonth()
    const checkMonth = () => {
      const nextMonth = currentManilaMonth()
      if (nextMonth === observedMonth) return
      observedMonth = nextMonth
      setLatestMonth(nextMonth)
      if (!month) setReload((count) => count + 1)
    }
    const interval = setInterval(checkMonth, 30_000)
    window.addEventListener('focus', checkMonth)
    document.addEventListener('visibilitychange', checkMonth)
    return () => {
      clearInterval(interval)
      window.removeEventListener('focus', checkMonth)
      document.removeEventListener('visibilitychange', checkMonth)
    }
  }, [month])

  function selectMonth(value) {
    if (value === '' || (/^\d{4}-(0[1-9]|1[0-2])$/.test(value) && value <= latestMonth)) {
      setMonth(value)
    }
  }

  return <section className="monthly-report" aria-labelledby="monthly-report-title">
    <div className="monthly-report-heading">
      <div>
        <h1 id="monthly-report-title">Monthly Financial Summary</h1>
        {current.state === 'ready' && <p className="monthly-report-date">
          {displayMonth(current.report.reporting_month)}
        </p>}
      </div>
      <div className="monthly-report-controls">
        <label>Reporting month
          <input type="month" value={month} max={latestMonth}
            onChange={(event) => selectMonth(event.target.value)} />
        </label>
        <button className="monthly-report-refresh" type="button" aria-label="Refresh monthly report"
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
    {current.state === 'loading' && <p className="monthly-report-notice" role="status">Loading monthly report…</p>}
    {current.state === 'error' && <div className="monthly-report-error" role="alert">
      <p>{current.error}</p>
      <button type="button" onClick={() => setReload((count) => count + 1)}>Try again</button>
    </div>}
    {current.state === 'ready' && <div className="monthly-report-body">
      <dl className="monthly-report-totals">
        <MoneyLine label="Gross Sales" value={current.report.gross_sales} />
        <MoneyLine label="Staff Commission" value={current.report.total_staff_commission} />
        <MoneyLine label="Business Share" value={current.report.total_business_share} />
      </dl>
      <div className="monthly-report-lower">
        <section className="monthly-report-surface monthly-report-payment" aria-labelledby="monthly-payment-title">
          <h2 id="monthly-payment-title">Payment Breakdown</h2>
          <dl>
            <MoneyLine label="Cash Sales" value={current.report.cash_sales} />
            <MoneyLine label="GCash Sales" value={current.report.gcash_sales} />
          </dl>
        </section>
        <section className="monthly-report-surface monthly-report-staff" aria-labelledby="monthly-staff-title">
          <h2 id="monthly-staff-title">Staff Performance</h2>
          {current.report.staff_performance.length === 0
            ? <p className="monthly-report-empty">No staff performance for this month.</p>
            : <table>
              <colgroup><col className="monthly-staff-name" /><col className="monthly-staff-sales" />
                <col className="monthly-staff-commission" /></colgroup>
              <thead><tr><th scope="col">Staff</th><th scope="col">Sales</th>
                <th scope="col">Commission</th></tr></thead>
              <tbody>{current.report.staff_performance.map((row) => <tr key={row.staff_id}>
                <th scope="row">{row.current_staff_name}</th>
                <td>{peso(row.attributed_sales)}</td>
                <td>{peso(row.total_staff_commission)}</td>
              </tr>)}</tbody>
            </table>}
        </section>
      </div>
      {current.report.completed_transaction_count === 0 &&
        <p className="monthly-report-notice">No completed sales for this month. Financial totals are zero.</p>}
    </div>}
  </section>
}
