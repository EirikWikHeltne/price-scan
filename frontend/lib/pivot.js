// Possible column names for the retailer identifier in a normalized/long table
export const RETAILER_ID_COLS = ['kilde', 'apotek', 'kjede', 'retailer', 'butikk', 'pharmacy']
// Possible column names for the price value in a normalized/long table
export const PRICE_VAL_COLS = ['pris', 'price', 'verdi', 'value']

// Columns that are never per-retailer prices
export const NON_PRICE_COLS = new Set([
  'id', 'produktid', 'produkt', 'merke', 'varenummer', 'kategori',
  'niva1', 'niva2', 'niva3', 'segment', 'ean', 'produsent',
  'sist_oppdatert', 'laveste_pris', 'hoyeste_pris', 'dato',
  // Long-format markers — if pivot ever fails to fire, don't let these
  // get picked up as retailer columns.
  ...RETAILER_ID_COLS, ...PRICE_VAL_COLS,
  // Synthetic aggregate fields we emit ourselves.
  'snitt', 'antall',
])

// Normalize retailer names to match prissammenligning column names
export function normalizeRetailerKey(name) {
  const n = String(name).toLowerCase().trim()
  if (n.includes('apotek 1') || n === 'apotek1') return 'apotek1'
  if (n.includes('farmasiet')) return 'farmasiet'
  if (n.includes('boots')) return 'boots'
  if (n.includes('vitusapotek') || n.includes('vitus apotek')) return 'vitusapotek'
  return n.replace(/\s+/g, '_')
}

/**
 * If history rows are in long/normalized format (one row per retailer per
 * date), pivot to wide format (one row per date, retailer prices as columns).
 * Otherwise return as-is.
 */
export function pivotIfNeeded(rows) {
  if (!rows?.length) return rows
  // Column existence is the right signal (a column can be present but null on
  // some rows); checking `!= null` on just the first row missed long-format
  // tables when row 0 happened to have a null retailer id.
  const first = rows[0]
  const retailerCol = RETAILER_ID_COLS.find(c => c in first)
  const priceCol = PRICE_VAL_COLS.find(c => c in first)
  if (!retailerCol || !priceCol) return rows

  const grouped = {}
  rows.forEach(row => {
    const date = row.dato?.slice?.(0, 10) || ''
    const vn = row.varenummer || ''
    const key = `${date}|${vn}`
    if (!grouped[key]) {
      grouped[key] = {
        dato: date,
        varenummer: vn,
        produkt: row.produkt,
        kategori: row.kategori,
        merke: row.merke,
      }
    }
    const rKey = normalizeRetailerKey(row[retailerCol])
    const price = Number(row[priceCol])
    // Pris 0 betyr at kjeden ikke fører produktet, ikke at det er gratis
    if (rKey && price > 0) {
      grouped[key][rKey] = price
    }
  })
  return Object.values(grouped).sort((a, b) => (a.dato || '').localeCompare(b.dato || ''))
}
