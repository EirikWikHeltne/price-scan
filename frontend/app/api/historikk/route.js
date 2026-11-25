import { getSupabase } from '@/lib/supabaseServer'
import { cacheHeaders } from '@/lib/cacheHeaders'
import { fetchHistoryRows, sinceDate } from '@/lib/historyRows'
import { NON_PRICE_COLS } from '@/lib/pivot'
import { parseDager } from '@/lib/parseDager'

export const dynamic = 'force-dynamic'

// Convert current prices from prissammenligning into history-like rows
function toHistoryRows(rows) {
  return rows.map(row => {
    const entry = {
      dato: row.sist_oppdatert?.slice(0, 10) || new Date().toISOString().slice(0, 10),
      varenummer: row.varenummer,
      produkt: row.produkt,
    }
    Object.keys(row).forEach(k => {
      if (!NON_PRICE_COLS.has(k)) entry[k] = row[k]
    })
    return entry
  })
}

// Fall back to current prices from prissammenligning when prishistorikk is
// unavailable or empty. Returns history-like rows, or null if nothing matches.
async function fetchCurrentPriceFallback(supabase, { varenummer, produkt }) {
  let query = supabase.from('prissammenligning').select('*')
  if (varenummer) {
    query = query.eq('varenummer', varenummer)
  } else if (produkt) {
    const safe = produkt.replace(/[(),.\\*"%_]/g, '')
    if (safe) query = query.ilike('produkt', `%${safe}%`)
  }
  const { data } = await query
  return data?.length ? toHistoryRows(data) : null
}

export async function GET(request) {
  let supabase
  try {
    supabase = getSupabase()
  } catch {
    return Response.json({ error: 'Server misconfiguration: missing env vars' }, { status: 500 })
  }

  const startedAt = performance.now()
  const { searchParams } = new URL(request.url)
  const produkt = searchParams.get('produkt')
  const varenummer = searchParams.get('varenummer')
  const dager = parseDager(searchParams.get('dager'), 30)

  const { data, error } = await fetchHistoryRows(supabase, {
    since: sinceDate(dager),
    varenummer,
    produkt,
  })

  if (error) {
    // If the table doesn't exist, fall back to current prices from prissammenligning
    if (error.code === '42P01' || error.message?.includes('does not exist')) {
      try {
        const rows = await fetchCurrentPriceFallback(supabase, { varenummer, produkt })
        if (rows) {
          return Response.json(rows, { headers: cacheHeaders(startedAt) })
        }
      } catch (_) { /* ignore fallback errors */ }

      return Response.json(
        { error: 'Prishistorikk-tabellen finnes ikke ennå', code: 'TABLE_NOT_FOUND' },
        { status: 404, headers: { 'Cache-Control': 'no-store' } }
      )
    }
    console.error('Supabase error:', error)
    return Response.json({ error: 'Failed to fetch data' }, { status: 500 })
  }

  // If prishistorikk exists but has no data for this product, fall back to prissammenligning
  if (!data.length) {
    const rows = await fetchCurrentPriceFallback(supabase, { varenummer, produkt })
    if (rows) {
      return Response.json(rows, { headers: cacheHeaders(startedAt) })
    }
  }

  return Response.json(data, { headers: cacheHeaders(startedAt) })
}
