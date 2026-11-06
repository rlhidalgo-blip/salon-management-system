const manila = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit', day: '2-digit',
})

export function manilaToday() {
  const parts = manila.formatToParts(new Date())
  const value = (type) => parts.find((part) => part.type === type).value
  return `${value('year')}-${value('month')}-${value('day')}`
}

export function shiftDate(day, days) {
  const date = new Date(`${day}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

export function monthBounds(month) {
  const [year, number] = month.split('-').map(Number)
  const last = new Date(Date.UTC(year, number, 0)).toISOString().slice(0, 10)
  return { from: `${month}-01`, through: last }
}

export function shiftMonth(month, offset) {
  const [year, number] = month.split('-').map(Number)
  const date = new Date(Date.UTC(year, number - 1 + offset, 1))
  return date.toISOString().slice(0, 7)
}

export function rangeDays(from, through, limit) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(through)) return false
  const first = new Date(`${from}T00:00:00Z`)
  const last = new Date(`${through}T00:00:00Z`)
  if (Number.isNaN(first.getTime()) || Number.isNaN(last.getTime()) ||
      first.toISOString().slice(0, 10) !== from || last.toISOString().slice(0, 10) !== through) return false
  const count = (last - first) / 86_400_000 + 1
  return count >= 1 && count <= limit
}

export function peso(value) {
  // Format only the backend's Decimal string; never compute money in JavaScript.
  const match = String(value).match(/^(-?)(\d+)(?:\.(\d{1,2}))?$/)
  if (!match) return '—'
  const grouped = match[2].replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `₱${match[1]}${grouped}.${(match[3] || '').padEnd(2, '0')}`
}
