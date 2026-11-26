// ISO-8601 week number for a given date (Monday-based, week 1 contains Jan 4th).
export function isoWeek(d) {
  const date = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()))
  const dayNum = (date.getUTCDay() + 6) % 7
  date.setUTCDate(date.getUTCDate() - dayNum + 3)
  const firstThursday = new Date(Date.UTC(date.getUTCFullYear(), 0, 4))
  const week = 1 + Math.round(
    ((date - firstThursday) / 86400000 - 3 + ((firstThursday.getUTCDay() + 6) % 7)) / 7
  )
  return { year: date.getUTCFullYear(), week }
}

// Monday (start) of the ISO week for a given date — used for human-readable labels.
export function isoWeekMonday(d) {
  const date = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()))
  const dayNum = (date.getUTCDay() + 6) % 7
  date.setUTCDate(date.getUTCDate() - dayNum)
  return date
}

export function weekMeta(dateStr) {
  const d = new Date(dateStr + 'T12:00:00Z')
  if (isNaN(d)) return null
  const { year, week } = isoWeek(d)
  const monday = isoWeekMonday(d)
  return {
    key: `${year}-W${String(week).padStart(2, '0')}`,
    week,
    year,
    monday: monday.toISOString().slice(0, 10),
  }
}
