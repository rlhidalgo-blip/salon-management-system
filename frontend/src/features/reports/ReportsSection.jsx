import { useState } from 'react'

import DailyFinancialSummary from './DailyFinancialSummary.jsx'
import MonthlyFinancialSummary from './MonthlyFinancialSummary.jsx'
import OperatingCalendar from './OperatingCalendar.jsx'
import WeekdaySales from './WeekdaySales.jsx'
import './ReportsSection.css'

export default function ReportsSection({ user, csrfToken, onRevalidateSession,
  calendarWritesEnabled = import.meta.env.DEV && import.meta.env.VITE_CALENDAR_WRITES_ENABLED === '1' }) {
  const [view, setView] = useState('daily')

  if (user.role !== 'Owner') {
    return <DailyFinancialSummary user={user} onRevalidateSession={onRevalidateSession} />
  }

  return <div className="reports-section">
    <nav className="reports-view-switch" aria-label="Report views">
      <button type="button" aria-pressed={view === 'daily'} onClick={() => setView('daily')}>Daily</button>
      <button type="button" aria-pressed={view === 'monthly'} onClick={() => setView('monthly')}>Monthly</button>
      <button type="button" aria-pressed={view === 'calendar'} onClick={() => setView('calendar')}>Calendar</button>
      <button type="button" aria-pressed={view === 'weekday'} onClick={() => setView('weekday')}>Weekday</button>
    </nav>
    {view === 'daily' && <DailyFinancialSummary user={user} onRevalidateSession={onRevalidateSession} />}
    {view === 'monthly' && <MonthlyFinancialSummary onRevalidateSession={onRevalidateSession} />}
    {view === 'calendar' && <OperatingCalendar csrfToken={csrfToken}
      writesEnabled={calendarWritesEnabled} onRevalidateSession={onRevalidateSession} />}
    {view === 'weekday' && <WeekdaySales onRevalidateSession={onRevalidateSession} />}
  </div>
}
