import { useEffect, useState } from 'react'

import { manilaToday, peso, rangeDays, shiftDate } from './businessDates.js'
import { getWeekdaySales } from './weekdaySalesApi.js'
import './OperatingCalendar.css'
import './WeekdaySales.css'

function WeekdayAverageChart({ rows }) {
  // Numeric conversion scales pixels only. Labels and averages come unchanged from the API.
  const values = rows.map((row) => row.average_gross_per_verified_open_day === null
    ? null : Number(row.average_gross_per_verified_open_day))
  const maximum = Math.max(0, ...values.filter((value) => Number.isFinite(value)))
  const hasAverage = values.some((value) => value !== null && Number.isFinite(value))
  return <figure className="weekday-chart-surface" aria-labelledby="weekday-chart-title">
    <p className="reports-eyebrow">Average gross sales</p>
    <figcaption id="weekday-chart-title">Average gross sales per verified Open day</figcaption>
    <p>Backend-calculated averages for historical dates verified Open by the Owner.</p>
    {!hasAverage && <div className="weekday-chart-empty">
      <span className="weekday-empty-bars" aria-hidden="true"><i /><i /><i /></span>
      <h3>Averages are not available yet</h3>
      <p>At least one verified Open historical date is needed for an average.</p>
    </div>}
    <div className="weekday-chart">
      {rows.map((row, index) => {
        const value = values[index]
        const available = value !== null && Number.isFinite(value)
        const height = available && maximum > 0 ? `${Math.max(0, value / maximum * 100)}%` : '0%'
        return <div className="weekday-chart-column" key={row.weekday_number}>
          <div className="weekday-chart-value">{available ? peso(row.average_gross_per_verified_open_day) : 'Unavailable'}</div>
          <div className="weekday-chart-track" aria-hidden="true">
            {available && <div className="weekday-chart-bar" style={{ height }} />}
          </div>
          <strong>{row.weekday.slice(0, 3)}</strong>
          <span>{row.verified_open_days} Open {row.verified_open_days === 1 ? 'day' : 'days'}</span>
        </div>
      })}
    </div>
  </figure>
}

function CoverageCard({ coverage }) {
  const verified = coverage.verified_open_days + coverage.verified_closed_days
  const percent = coverage.historical_days > 0
    ? Math.round(verified / coverage.historical_days * 100) : 0
  return <aside className="weekday-coverage-card" aria-label="Operating date coverage">
    <p className="reports-eyebrow">Data coverage</p>
    <h2>Verification status</h2>
    <div className="weekday-coverage-ring" style={{ '--coverage-percent': `${percent}%` }}
      aria-label={`${percent}% of historical dates verified`}>
      <div><strong>{percent}%</strong><span>verified</span></div>
    </div>
    <dl className="weekday-coverage-counts">
      <div><dt>Open</dt><dd>{coverage.verified_open_days}</dd></div>
      <div><dt>Closed</dt><dd>{coverage.verified_closed_days}</dd></div>
      <div><dt>Unknown</dt><dd>{coverage.unknown_days}</dd></div>
      <div><dt>Unconfirmed plans</dt><dd>{coverage.unconfirmed_planned_days}</dd></div>
    </dl>
    {coverage.incomplete_coverage && <p className="calendar-warning">{coverage.unverified_days} historical dates still need review.</p>}
  </aside>
}

function reportError(error) {
  if (error.status === 403) return 'You do not have permission to view weekday analytics.'
  if (error.status === 422) return 'Choose a valid range of up to 366 dates ending no later than today in Manila.'
  return 'Weekday analytics are temporarily unavailable. Please try again.'
}

export default function WeekdaySales({ onRevalidateSession }) {
  const [today, setToday] = useState(manilaToday)
  const [from, setFrom] = useState(() => shiftDate(manilaToday(), -27))
  const [through, setThrough] = useState(manilaToday)
  const [range, setRange] = useState(() => ({ from: shiftDate(manilaToday(), -27), through: manilaToday() }))
  const [rangeError, setRangeError] = useState('')
  const [reload, setReload] = useState(0)
  const [result, setResult] = useState({ state: 'loading', report: null, error: '' })

  useEffect(() => {
    const controller = new AbortController()
    setResult({ state: 'loading', report: null, error: '' })
    getWeekdaySales(range.from, range.through, controller.signal).then((report) => {
      if (!controller.signal.aborted) setResult({ state: 'ready', report, error: '' })
    }).catch(async (error) => {
      if (controller.signal.aborted) return
      if (error.status === 401) {
        try { if (!await onRevalidateSession()) return } catch { /* Keep retry available. */ }
      }
      if (!controller.signal.aborted) setResult({ state: 'error', report: null, error: reportError(error) })
    })
    return () => controller.abort()
  }, [range, reload, onRevalidateSession])

  useEffect(() => {
    const check = () => {
      const next = manilaToday()
      if (next !== today) { setToday(next); setReload((count) => count + 1) }
    }
    const interval = setInterval(check, 30_000)
    window.addEventListener('focus', check)
    return () => { clearInterval(interval); window.removeEventListener('focus', check) }
  }, [today])

  function applyRange(event) {
    event.preventDefault()
    if (!rangeDays(from, through, 366) || through > today) {
      setRangeError('Choose 1 to 366 valid dates, ending no later than today in Manila.')
      return
    }
    setRangeError('')
    setRange({ from, through })
  }

  const report = result.report
  return <section className="weekday-sales" aria-labelledby="weekday-sales-title">
    <header className="reports-feature-heading">
      <div><p className="reports-eyebrow">Reports / Weekday analytics</p>
        <h1 id="weekday-sales-title">Weekday Sales Analytics</h1>
        <p>Compare gross sales by weekday using verified operating history.</p></div>
      <button type="button" className="reports-secondary" disabled={result.state === 'loading'}
        onClick={() => setReload((count) => count + 1)}>Refresh data</button>
    </header>
    <form className="calendar-range weekday-filters" onSubmit={applyRange}>
      <label>From <input type="date" value={from} max={today} onChange={(event) => setFrom(event.target.value)} /></label>
      <label>Through <input type="date" value={through} max={today} onChange={(event) => setThrough(event.target.value)} /></label>
      <button type="submit">Show weekdays</button>
    </form>
    {rangeError && <p role="alert">{rangeError}</p>}
    {result.state === 'loading' && <p role="status">Loading weekday sales…</p>}
    {result.state === 'error' && <div role="alert"><p>{result.error}</p>
      <button type="button" onClick={() => setReload((count) => count + 1)}>Try again</button></div>}
    {result.state === 'ready' && <>
      <p className="weekday-period">Period: {report.from} through {report.through} (Asia/Manila). As of {report.as_of}.</p>
      <div className="weekday-overview">
        <WeekdayAverageChart rows={report.weekdays} />
        <CoverageCard coverage={report.coverage} />
      </div>
      {report.coverage.incomplete_coverage && <p className="calendar-warning" role="status">
        Partial averages: {report.coverage.unverified_days} historical dates are unverified
        ({report.coverage.unknown_days} Unknown; {report.coverage.unconfirmed_planned_days} unconfirmed Planned Closed).
      </p>}
      {report.coverage.closed_dates_with_sales > 0 && <p className="calendar-anomaly" role="alert">
        {report.coverage.closed_dates_with_sales} verified Closed dates contain completed sales. Their sales remain in gross totals but are excluded from verified Open averages.
      </p>}
      <p className="weekday-method-note">Gross sales include all Completed sales in this period. Averages use only verified Open historical dates, including zero-sales days.</p>
      <section className="weekday-detail-card">
        <div className="weekday-detail-heading"><div><p className="reports-eyebrow">Supporting detail</p><h2>Weekday breakdown</h2></div>
          <span>{report.from} through {report.through}</span></div>
        <div className="calendar-scroll"><table><thead><tr>
        <th scope="col">Weekday</th><th scope="col">Gross sales</th><th scope="col">Historical gross</th>
        <th scope="col">Verified Open gross</th><th scope="col">Average / verified Open day</th>
        <th scope="col">Open days</th><th scope="col">Closed days</th><th scope="col">Unknown days</th>
        <th scope="col">Unconfirmed plans</th><th scope="col">Provisional today</th>
        <th scope="col">Closed dates with sales</th>
      </tr></thead><tbody>{report.weekdays.map((row) => <tr key={row.weekday_number}>
        <th scope="row">{row.weekday}</th><td>{peso(row.gross_sales)}</td>
        <td>{peso(row.historical_gross_sales)}</td><td>{peso(row.verified_open_gross_sales)}</td>
        <td>{row.average_gross_per_verified_open_day === null ? 'Unavailable' : peso(row.average_gross_per_verified_open_day)}</td>
        <td>{row.verified_open_days}</td><td>{row.verified_closed_days}</td><td>{row.unknown_days}</td>
        <td>{row.unconfirmed_planned_days}</td><td>{peso(row.provisional_today_gross_sales)}</td>
        <td>{row.closed_dates_with_sales}</td>
      </tr>)}</tbody></table></div>
      </section>
      {report.coverage.verified_open_days === 0 && <p>No verified Open historical dates are available for an average.</p>}
      <p>Today’s completed sales are provisional and do not contribute to operating-day averages.</p>
    </>}
  </section>
}
