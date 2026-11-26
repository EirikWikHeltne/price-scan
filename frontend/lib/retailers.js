export const KNOWN_RETAILER_STYLES = {
  farmasiet:   { label: 'Farmasiet',   color: '#2563EB' },
  boots:       { label: 'Boots',       color: '#E11D48' },
  vitusapotek: { label: 'Vitusapotek', color: '#059669' },
  apotek1:     { label: 'Apotek 1',    color: '#7C3AED' },
}

export const NON_RETAILER_COLS = new Set([
  'id', 'produktid', 'produkt', 'merke', 'varenummer', 'kategori',
  'sist_oppdatert', 'laveste_pris', 'hoyeste_pris', 'dato',
  'snitt', 'antall',
])

export const FALLBACK_COLORS = ['#D97706', '#0891B2', '#BE185D', '#65A30D', '#DC2626', '#9333EA']

export function deriveRetailers(data) {
  if (!data?.length) return []
  const keys = []
  const seen = new Set()
  data.forEach(row => {
    Object.keys(row).forEach(k => {
      if (!NON_RETAILER_COLS.has(k) && !seen.has(k)) {
        const val = row[k]
        if (val !== null && val !== undefined && !isNaN(Number(val))) {
          seen.add(k)
          keys.push(k)
        }
      }
    })
  })
  let colorIdx = 0
  return keys.map(key => ({
    key,
    label: KNOWN_RETAILER_STYLES[key]?.label || (key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ')),
    color: KNOWN_RETAILER_STYLES[key]?.color || FALLBACK_COLORS[colorIdx++ % FALLBACK_COLORS.length],
  }))
}
