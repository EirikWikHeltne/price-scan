const collator = new Intl.Collator('nb', { numeric: true, sensitivity: 'base' })

// Sammenligner to celleverdier for tabellsortering. Manglende verdier havner
// alltid nederst, uansett retning, og tekst sorteres etter norsk alfabet.
export function compareValues(a, b, dir = 'asc') {
  const aMissing = a === null || a === undefined || a === ''
  const bMissing = b === null || b === undefined || b === ''
  if (aMissing || bMissing) return aMissing === bMissing ? 0 : aMissing ? 1 : -1
  const result = typeof a === 'number' && typeof b === 'number'
    ? a - b
    : collator.compare(String(a), String(b))
  return dir === 'asc' ? result : -result
}
