// Felles produktsøk: treff på produktnavn, merke eller varenummer.
// Varenummer kan komme som tall fra databasen, derfor String().
export function matchesSearch(row, query) {
  const q = String(query ?? '').trim().toLowerCase()
  if (!q) return true
  return ['produkt', 'merke', 'varenummer'].some(field =>
    String(row?.[field] ?? '').toLowerCase().includes(q)
  )
}
