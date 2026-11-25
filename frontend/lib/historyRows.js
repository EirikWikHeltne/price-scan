import { fetchAllRows } from './fetchAllRows.js'
import { pivotIfNeeded, RETAILER_ID_COLS, PRICE_VAL_COLS } from './pivot.js'

const META_COLS = ['produkt', 'kategori', 'merke']

// Kolonneoppsettet til prishistorikk endrer seg ikke mellom kall, så det
// leses én gang per serverinstans i stedet for foran hver spørring.
let cachedLayout = null

async function getLayout(supabase) {
  if (cachedLayout) return { layout: cachedLayout }
  // Én rad for å finne ut hvilke kolonner tabellen har
  const probe = await supabase.from('prishistorikk').select('*').limit(1)
  if (probe.error) return { error: probe.error }
  const sample = probe.data?.[0]
  if (!sample) return { layout: null } // tom tabell

  const retailerCol = RETAILER_ID_COLS.find(c => c in sample)
  const priceCol = PRICE_VAL_COLS.find(c => c in sample)
  const isLong = Boolean(retailerCol && priceCol)
  cachedLayout = {
    isLong,
    priceCol,
    columns: isLong
      ? ['dato', 'varenummer', ...META_COLS.filter(c => c in sample), retailerCol, priceCol].join(',')
      : '*',
    // Entydig rekkefølge, slik at parallelle sider ikke overlapper
    orderBy: ['dato', 'varenummer', isLong ? retailerCol : null, 'id'].filter(c => c && c in sample),
  }
  return { layout: cachedLayout }
}

// Henter prishistorikk og returnerer den i bredt format (én rad per dato og
// produkt, med én kolonne per kjede).
//
// Tabellen har én rad per kjede per produkt per dag, så noen måneder med
// historikk er flere hundre tusen rader. For å holde det raskt:
//  - hentes bare kolonnene som brukes
//  - hoppes det over rader med pris 0 (kjeden fører ikke produktet — det er
//    ikke en pris, og skal ikke telle med i snitt eller tegnes i grafer)
//  - hentes sidene parallelt (se fetchAllRows)
//
// `filter` er valgfri: { since: 'YYYY-MM-DD', varenummer, produkt }.
export async function fetchHistoryRows(supabase, filter = {}) {
  const { layout, error: layoutError } = await getLayout(supabase)
  if (layoutError) return { data: null, error: layoutError }
  if (!layout) return { data: [], error: null }
  const { isLong, priceCol, columns, orderBy } = layout

  const buildQuery = () => {
    let query = supabase.from('prishistorikk').select(columns, { count: 'exact' })
    if (isLong) query = query.gt(priceCol, 0)
    if (filter.varenummer) {
      query = query.eq('varenummer', filter.varenummer)
    } else if (filter.produkt) {
      const safe = filter.produkt.replace(/[(),.\\*"%_]/g, '')
      if (safe) query = query.ilike('produkt', `%${safe}%`)
    }
    if (filter.since) query = query.gte('dato', filter.since)
    for (const col of orderBy) query = query.order(col, { ascending: true })
    return query
  }

  const { data, error } = await fetchAllRows(buildQuery)
  if (error) return { data: null, error }
  return { data: pivotIfNeeded(data), error: null }
}

// 'YYYY-MM-DD' for `dager` dager siden, eller null når dager er 0 (= alt).
export function sinceDate(dager) {
  if (!(dager > 0)) return null
  const since = new Date()
  since.setDate(since.getDate() - dager)
  return since.toISOString().slice(0, 10)
}
