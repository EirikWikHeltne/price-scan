// Intl-formatterere er dyre å opprette; gjenbruk dem i stedet for å kalle
// toLocaleString med opsjoner for hver celle.
const fmt2 = new Intl.NumberFormat('nb-NO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const fmt0 = new Intl.NumberFormat('nb-NO', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
const dateShort = new Intl.DateTimeFormat('nb-NO', { day: 'numeric', month: 'short' })
const dateLong = new Intl.DateTimeFormat('nb-NO', { day: 'numeric', month: 'short', year: 'numeric' })

export function fmt(val) {
  if (val === null || val === undefined) return ''
  return fmt2.format(Number(val))
}

export function fmtShort(val) {
  if (val === null || val === undefined) return ''
  return fmt0.format(Number(val))
}

export function fmtDateShort(val) {
  return dateShort.format(new Date(val))
}

export function fmtDate(val) {
  return dateLong.format(new Date(val))
}
