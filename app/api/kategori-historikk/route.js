import { getSupabase } from '@/lib/supabaseServer'
import { cacheHeaders } from '@/lib/cacheHeaders'
import { fetchAllRows } from '@/lib/fetchAllRows'
import { fetchHistoryRows, sinceDate } from '@/lib/historyRows'
import { NON_PRICE_COLS } from '@/lib/pivot'
import { parseDager } from '@/lib/parseDager'

export const dynamic = 'force-dynamic'

/**
 * Aggregate rows (one product per row per date) into category averages.
 * Returns one row per (dato, kategori) with averaged retailer prices and
 * an overall `snitt` field that is the cross-retailer average.
 */
function aggregateByCategoryAndDate(rows) {
  const retailerKeys = new Set()
  rows.forEach(row => {
    Object.keys(row).forEach(k => {
      if (!NON_PRICE_COLS.has(k)) {
        const v = row[k]
        if (v != null && v !== '' && !isNaN(Number(v))) retailerKeys.add(k)
      }
    })
  })

  const grouped = {}
  rows.forEach(row => {
    const date = (row.dato || row.sist_oppdatert || '').slice?.(0, 10) || ''
    const cat = row.kategori
    if (!date || !cat) return
    const gkey = `${date}|${cat}`
    if (!grouped[gkey]) grouped[gkey] = { dato: date, kategori: cat, sums: {}, counts: {}, products: new Set() }
    if (row.varenummer) grouped[gkey].products.add(row.varenummer)
    retailerKeys.forEach(rk => {
      const v = row[rk]
      if (v != null && v !== '' && !isNaN(Number(v))) {
        grouped[gkey].sums[rk] = (grouped[gkey].sums[rk] || 0) + Number(v)
        grouped[gkey].counts[rk] = (grouped[gkey].counts[rk] || 0) + 1
      }
    })
  })

  return Object.values(grouped)
    .map(g => {
      const entry = { dato: g.dato, kategori: g.kategori, antall: g.products.size }
      const retailerMeans = []
      Object.keys(g.sums).forEach(rk => {
        const mean = g.sums[rk] / g.counts[rk]
        entry[rk] = +mean.toFixed(2)
        retailerMeans.push(mean)
      })
      // Mean-of-means so retailers with more product coverage don't dominate.
      entry.snitt = retailerMeans.length
        ? +(retailerMeans.reduce((s, v) => s + v, 0) / retailerMeans.length).toFixed(2)
        : null
      return entry
    })
    .sort((a, b) =>
      a.dato === b.dato ? a.kategori.localeCompare(b.kategori) : a.dato.localeCompare(b.dato)
    )
}

async function loadCurrentSnapshot(supabase) {
  const { data, error } = await fetchAllRows(() => supabase.from('prissammenligning').select('*', { count: 'exact' }).order('id'))
  if (error || !data?.length) return []
  return data.map(row => ({
    ...row,
    dato: row.sist_oppdatert?.slice(0, 10) || new Date().toISOString().slice(0, 10),
  }))
}

async function enrichCategories(supabase, rows) {
  const missing = rows.filter(r => !r.kategori && r.varenummer)
  if (!missing.length) return rows
  const { data, error } = await fetchAllRows(
    () => supabase.from('prissammenligning').select('varenummer, kategori, merke, produkt', { count: 'exact' }).order('id')
  )
  if (error || !data?.length) return rows
  const byVn = {}
  data.forEach(p => { if (p.varenummer) byVn[p.varenummer] = p })
  rows.forEach(r => {
    if (!r.kategori && r.varenummer && byVn[r.varenummer]) {
      r.kategori = byVn[r.varenummer].kategori
      r.merke = r.merke || byVn[r.varenummer].merke
      r.produkt = r.produkt || byVn[r.varenummer].produkt
    }
  })
  return rows
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
  const dager = parseDager(searchParams.get('dager'), 90)

  const { data, error } = await fetchHistoryRows(supabase, { since: sinceDate(dager) })

  if (error) {
    if (error.code === '42P01' || error.message?.includes('does not exist')) {
      const snapshot = await loadCurrentSnapshot(supabase)
      if (snapshot.length) {
        return Response.json(aggregateByCategoryAndDate(snapshot), {
          headers: { ...cacheHeaders(startedAt), 'X-Source': 'snapshot' },
        })
      }
      return Response.json(
        { error: 'Prishistorikk-tabellen finnes ikke ennå', code: 'TABLE_NOT_FOUND' },
        { status: 404, headers: { 'Cache-Control': 'no-store' } }
      )
    }
    console.error('Supabase error:', error)
    return Response.json({ error: 'Failed to fetch data' }, { status: 500 })
  }

  let pivoted = data

  if (!pivoted.length) {
    const snapshot = await loadCurrentSnapshot(supabase)
    pivoted = snapshot
  } else {
    pivoted = await enrichCategories(supabase, pivoted)
  }

  return Response.json(aggregateByCategoryAndDate(pivoted), { headers: cacheHeaders(startedAt) })
}
