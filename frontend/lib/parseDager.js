// Leser ?dager= fra en forespørsel. 0 betyr «hele historikken». Ugyldige
// eller negative verdier gir standardverdien i stedet for å hente alt.
export function parseDager(value, fallback) {
  if (value === null || value === undefined || value === '') return fallback
  const n = Number(value)
  if (!Number.isInteger(n) || n < 0) return fallback
  return Math.min(n, 3650)
}
