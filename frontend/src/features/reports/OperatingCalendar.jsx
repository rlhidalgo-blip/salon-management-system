import { useEffect, useState } from 'react'

import { manilaToday, monthBounds, peso, shiftMonth } from './businessDates.js'
import { bulkVerifyOpen, getOperatingDayHistory, getOperatingDays, putOperatingDay } from './operatingCalendarApi.js'
import './OperatingCalendar.css'

const statuses = ['Unknown', 'Open', 'Closed', 'PlannedClosed']
const weekdayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const monthTitle = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'long', year: 'numeric' })

function calendarCells(from, through) {
  const leading = (new Date(`${from}T00:00:00Z`).getUTCDay() + 6) % 7
  const days = Number(through.slice(-2))
  const count = Math.ceil((leading + days) / 7) * 7
  return Array.from({ length: count }, (_, index) => {
    const number = index - leading + 1
    return number >= 1 && number <= days ? `${from.slice(0, 7)}-${String(number).padStart(2, '0')}` : null
  })
}

function statusLabel(day, today) {
  if (day.status === 'PlannedClosed') {
    return day.business_date < today ? 'Planned closure — outcome unconfirmed' : 'Planned Closed'
  }
  return day.status
}

function calendarError(error) {
  if (error.code === 'completed_sales_on_date') return 'This date has completed sales and cannot be marked Closed. Review its sales or choose another status.'
  if (error.code === 'operating_day_changed') return 'This date changed since you reviewed it. The calendar has been refreshed; review it before trying again.'
  if (error.status === 404) return 'Calendar editing is unavailable. This view is read-only.'
  if (error.status === 403) return 'You do not have permission to manage the operating calendar.'
  if (error.status === 422) return 'Check the date, status, and closure reason, then try again.'
  return 'The calendar request failed. Please try again.'
}

export default function OperatingCalendar({ csrfToken, onRevalidateSession, writesEnabled = false }) {
  const [today, setToday] = useState(manilaToday)
  const [month, setMonth] = useState(() => manilaToday().slice(0, 7))
  const [selectedDay, setSelectedDay] = useState(manilaToday)
  const [reload, setReload] = useState(0)
  const [result, setResult] = useState({ state: 'loading', days: [], error: '' })
  const [editDay, setEditDay] = useState(null)
  const [status, setStatus] = useState('Unknown')
  const [reason, setReason] = useState('')
  const [selected, setSelected] = useState([])
  const [preview, setPreview] = useState(false)
  const [historyDay, setHistoryDay] = useState('')
  const [history, setHistory] = useState({ state: 'idle', entries: [], error: '' })
  const [saving, setSaving] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [gateBlocked, setGateBlocked] = useState(false)
  const editable = writesEnabled && !gateBlocked
  const range = monthBounds(month)

  useEffect(() => {
    const controller = new AbortController()
    setResult({ state: 'loading', days: [], error: '' })
    getOperatingDays(range.from, range.through, controller.signal).then((days) => {
      if (!controller.signal.aborted) setResult({ state: 'ready', days, error: '' })
    }).catch(async (error) => {
      if (controller.signal.aborted) return
      if (error.status === 401) {
        try { if (!await onRevalidateSession()) return } catch { /* Keep retry available. */ }
      }
      if (!controller.signal.aborted) setResult({ state: 'error', days: [], error: calendarError(error) })
    })
    return () => controller.abort()
  }, [month, reload, onRevalidateSession])

  useEffect(() => {
    if (!historyDay) return undefined
    const controller = new AbortController()
    setHistory({ state: 'loading', entries: [], error: '' })
    getOperatingDayHistory(historyDay, controller.signal).then((entries) => {
      if (!controller.signal.aborted) setHistory({ state: 'ready', entries, error: '' })
    }).catch(async (error) => {
      if (controller.signal.aborted) return
      if (error.status === 401) {
        try { if (!await onRevalidateSession()) return } catch { /* Keep retry available. */ }
      }
      if (!controller.signal.aborted) setHistory({ state: 'error', entries: [], error: calendarError(error) })
    })
    return () => controller.abort()
  }, [historyDay, reload, onRevalidateSession])

  useEffect(() => {
    const check = () => {
      const next = manilaToday()
      if (next !== today) { setToday(next); setReload((count) => count + 1) }
    }
    const interval = setInterval(check, 30_000)
    window.addEventListener('focus', check)
    return () => { clearInterval(interval); window.removeEventListener('focus', check) }
  }, [today])

  function chooseMonth(next) {
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(next) || next < '0001-01' || next > '9999-12') return
    setFeedback('')
    setEditDay(null)
    setHistoryDay('')
    setSelected([])
    setPreview(false)
    setSelectedDay(next === today.slice(0, 7) ? today : `${next}-01`)
    setMonth(next)
  }

  function beginEdit(day) {
    setEditDay(day.business_date)
    setStatus(day.status)
    setReason(day.closure_reason || '')
    setFeedback('')
  }

  function toggleSelection(day) {
    setSelected((current) => current.includes(day) ? current.filter((item) => item !== day) : [...current, day])
    setPreview(false)
  }

  async function handleWriteError(error) {
    if (error.status === 401) {
      try { await onRevalidateSession() } catch { /* Keep the error visible. */ }
    }
    if (error.status === 404) setGateBlocked(true)
    if (error.code === 'operating_day_changed' || error.code === 'completed_sales_on_date') {
      setEditDay(null)
      setSelected([])
      setPreview(false)
      setReload((count) => count + 1)
    }
    setFeedback(error.status === 404 ? '' : calendarError(error))
  }

  async function saveDay(event) {
    event.preventDefault()
    if (!editable || saving) return
    const day = result.days.find((item) => item.business_date === editDay)
    if (!day) return
    const closure = status === 'Closed' || status === 'PlannedClosed'
    const cleanReason = reason.trim()
    if (closure && (!cleanReason || cleanReason.length > 500)) {
      setFeedback('Enter a closure reason of 1 to 500 characters.')
      return
    }
    setSaving(true)
    setFeedback('')
    try {
      await putOperatingDay(day.business_date, status, closure ? cleanReason : null, day.version, csrfToken)
      setEditDay(null)
      setSelected([])
      setPreview(false)
      setFeedback(`${day.business_date} updated.`)
      setReload((count) => count + 1)
    } catch (error) { await handleWriteError(error) }
    finally { setSaving(false) }
  }

  async function confirmBulk() {
    if (!editable || saving || !preview || !selected.length) return
    const dates = selected.map((value) => {
      const day = result.days.find((item) => item.business_date === value)
      return { business_date: value, expected_version: day.version }
    })
    setSaving(true)
    setFeedback('')
    try {
      const response = await bulkVerifyOpen(dates, csrfToken)
      setFeedback(`${response.changed_count} dates verified Open.`)
      setSelected([])
      setPreview(false)
      setReload((count) => count + 1)
    } catch (error) { await handleWriteError(error) }
    finally { setSaving(false) }
  }

  const editing = result.days.find((day) => day.business_date === editDay)
  const bulkDates = selected.slice().sort()
  const focusedDay = result.days.find((day) => day.business_date === selectedDay)
  const daysByDate = new Map(result.days.map((day) => [day.business_date, day]))
  const cells = calendarCells(range.from, range.through)
  const title = monthTitle.format(new Date(`${month}-01T00:00:00Z`))
  const selectedTitle = monthTitle.format(new Date(`${selectedDay}T00:00:00Z`)).replace(/ \d{4}$/, '')

  return <section className="operating-calendar" aria-labelledby="operating-calendar-title">
    <header className="reports-feature-heading">
      <div><p className="reports-eyebrow">Reports / Operating calendar</p>
        <h1 id="operating-calendar-title">Operating Calendar</h1>
        <p>Review business dates and their verified operating status. Sales activity alone never verifies Open.</p></div>
      <button type="button" className="reports-secondary" disabled={result.state === 'loading'}
        onClick={() => setReload((count) => count + 1)}>Refresh data</button>
    </header>
    {!editable && <p className="calendar-notice" role="status"><span aria-hidden="true">ⓘ</span>
      Calendar editing is unavailable. This view is read-only.</p>}
    <div className="calendar-period-note">Showing {range.from} through {range.through} · Asia/Manila business dates</div>
    {feedback && <p role="alert">{feedback}</p>}
    {result.state === 'loading' && <p role="status">Loading operating dates…</p>}
    {result.state === 'error' && <div role="alert"><p>{result.error}</p>
      <button type="button" onClick={() => setReload((count) => count + 1)}>Try again</button></div>}
    {result.state === 'ready' && <>
      {result.days.length === 0 ? <p>No operating dates were returned.</p> :
        <div className="calendar-layout">
          <div className="calendar-card">
            <div className="calendar-month-controls" aria-label="Calendar month navigation">
              <button type="button" className="calendar-square-button" aria-label="Previous month"
                onClick={() => chooseMonth(shiftMonth(month, -1))}>←</button>
              <div className="calendar-month-title"><h2>{title}</h2><span>Asia/Manila business dates</span></div>
              <button type="button" className="calendar-square-button" aria-label="Next month"
                onClick={() => chooseMonth(shiftMonth(month, 1))}>→</button>
              <button type="button" className="reports-secondary" onClick={() => chooseMonth(today.slice(0, 7))}>Today</button>
            </div>
            <div className="calendar-legend" role="group" aria-label="Operating status legend">
              {statuses.filter((value) => value !== 'Unknown').concat('Unknown').map((value) =>
                <span key={value} className={`calendar-legend-${value.toLowerCase()}`}>
                  <i aria-hidden="true" />{value === 'PlannedClosed' ? 'Planned Closed' : value}</span>)}
            </div>
            <div className="calendar-month-grid" role="group" aria-label={`${title} operating dates`}>
              {weekdayNames.map((name) => <div key={name} className="calendar-weekday">{name}</div>)}
              {cells.map((date, index) => {
                const day = daysByDate.get(date)
                if (!date) return <div key={`blank-${index}`} className="calendar-blank" aria-hidden="true" />
                if (!day) return <div key={date} className="calendar-blank" aria-hidden="true" />
                const selectable = editable && date < today && day.status === 'Unknown'
                return <div key={date} className={`calendar-day calendar-status-${day.status.toLowerCase()}`}>
                  <button type="button" className="calendar-day-select" aria-label={`${date}: ${statusLabel(day, today)}`}
                    aria-pressed={selectedDay === date} onClick={() => { setSelectedDay(date); setHistoryDay(date); setEditDay(null) }}>
                    <span className="calendar-day-number">{Number(date.slice(-2))}{date === today && <span className="calendar-today-label">Today</span>}</span>
                    <span className="calendar-day-status"><i aria-hidden="true" />{day.status === 'PlannedClosed' ? 'Planned Closed' : day.status}</span>
                    <span className="calendar-day-sales">{peso(day.gross_sales)}</span>
                    <span className="calendar-day-completed">{day.completed_transaction_count} completed</span>
                    {day.inconsistency && <span className="calendar-day-anomaly">Sales on Closed date</span>}
                  </button>
                  {selectable && <label className="calendar-day-review"><input type="checkbox"
                    aria-label={`Select ${date} for Open verification`} checked={selected.includes(date)}
                    onChange={() => toggleSelection(date)} /> Review</label>}
                </div>
              })}
            </div>
          </div>
          <aside className="calendar-details" aria-label={`Details for ${selectedDay}`}>
            {focusedDay ? <>
              <p className="reports-eyebrow">Selected business date</p>
              <h2>{selectedTitle} {Number(selectedDay.slice(-2))}, {selectedDay.slice(0, 4)}</h2>
              <span className={`calendar-detail-badge calendar-status-${focusedDay.status.toLowerCase()}`}>
                <i aria-hidden="true" />{statusLabel(focusedDay, today)}
              </span>
              <dl className="calendar-detail-values">
                <div><dt>Gross sales</dt><dd>{peso(focusedDay.gross_sales)}</dd></div>
                <div><dt>Completed sales</dt><dd>{focusedDay.completed_transaction_count}</dd></div>
                <div><dt>Closure reason</dt><dd>{focusedDay.closure_reason || 'None recorded'}</dd></div>
              </dl>
              {focusedDay.inconsistency && <p className="calendar-anomaly" role="alert">Closed with completed sales. Review this inconsistency.</p>}
              <p className="calendar-detail-note">Sales activity does not verify operating status.</p>
              {!historyDay && <button type="button" className="reports-secondary calendar-history-button"
                onClick={() => setHistoryDay(selectedDay)}>View audit history</button>}
              {editable && <button type="button" onClick={() => beginEdit(focusedDay)} disabled={saving}>Edit date</button>}
            </> : <p>Select a date to review its details.</p>}
      {editable && selected.length > 0 && <section aria-label="Bulk Open verification" className="calendar-panel">
        <h2>Bulk Open verification</h2>
        <p>{selected.length} historical Unknown dates selected. Review them, including zero-sales dates, before confirming Open.</p>
        <button type="button" disabled={saving} onClick={() => setPreview(true)}>Preview selected dates</button>
        {preview && <div><p>Confirm these {bulkDates.length} dates as verified Open:</p>
          <ul>{bulkDates.map((day) => <li key={day}>{day}</li>)}</ul>
          <button type="button" disabled={saving} onClick={confirmBulk}>Confirm {bulkDates.length} Open dates</button>{' '}
          <button type="button" disabled={saving} onClick={() => setPreview(false)}>Cancel preview</button>
        </div>}
      </section>}
      {editable && editing && <form className="calendar-panel" onSubmit={saveDay} aria-label={`Edit ${editing.business_date}`}>
        <h2>Edit {editing.business_date}</h2>
        <p>Current: {statusLabel(editing, today)} (version {editing.version}).</p>
        <label>Status <select value={status} onChange={(event) => setStatus(event.target.value)}>
          {statuses.filter((value) => value === 'Unknown' || value === 'PlannedClosed' &&
            (editing.business_date > today || editing.status === 'PlannedClosed') ||
            value !== 'PlannedClosed' && editing.business_date <= today).map((value) =>
            <option key={value} value={value}>{value}</option>)}</select></label>
        {(status === 'Closed' || status === 'PlannedClosed') && <label>Closure reason
          <textarea value={reason} maxLength={500} required onChange={(event) => setReason(event.target.value)} />
        </label>}
        {status === 'Closed' && editing.completed_transaction_count > 0 &&
          <p role="alert">Completed sales exist on this date. It cannot be marked Closed.</p>}
        <button type="submit" disabled={saving || status === 'Closed' && editing.completed_transaction_count > 0}>Save correction</button>{' '}
        <button type="button" disabled={saving} onClick={() => setEditDay(null)}>Cancel</button>
      </form>}
    {historyDay && <section className="calendar-panel" aria-label={`History for ${historyDay}`}>
      <h2>History for {historyDay}</h2>
      <button type="button" onClick={() => setHistoryDay('')}>Close history</button>
      {history.state === 'loading' && <p role="status">Loading history…</p>}
      {history.state === 'error' && <p role="alert">{history.error}</p>}
      {history.state === 'ready' && (history.entries.length === 0 ? <p>No recorded changes for this date.</p> :
        <ol>{history.entries.map((entry, index) => <li key={`${entry.version}-${index}`}>
          {entry.previous_status} → {entry.status} (version {entry.previous_version} → {entry.version});
          {' '}reason: {entry.previous_reason || 'none'} → {entry.closure_reason || 'none'};
          {' '}actor #{entry.actor_user_id};
          {' '}{entry.occurred_at}{entry.bulk && '; bulk verification'}
        </li>)}</ol>)}
    </section>}
          </aside>
        </div>}
    </>}
  </section>
}
