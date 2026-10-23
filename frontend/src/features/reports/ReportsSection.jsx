import { useState } from 'react'

import DailyFinancialSummary from './DailyFinancialSummary.jsx'
import MonthlyFinancialSummary from './MonthlyFinancialSummary.jsx'
import './ReportsSection.css'

export default function ReportsSection({ user, onRevalidateSession }) {
  const [view, setView] = useState('daily')

  if (user.role !== 'Owner') {
    return <DailyFinancialSummary user={user} onRevalidateSession={onRevalidateSession} />
  }

  return <div className="reports-section">
    <nav className="reports-view-switch" aria-label="Report views">
      <button type="button" aria-pressed={view === 'daily'} onClick={() => setView('daily')}>Daily</button>
      <button type="button" aria-pressed={view === 'monthly'} onClick={() => setView('monthly')}>Monthly</button>
    </nav>
    {view === 'daily'
      ? <DailyFinancialSummary user={user} onRevalidateSession={onRevalidateSession} />
      : <MonthlyFinancialSummary onRevalidateSession={onRevalidateSession} />}
  </div>
}
