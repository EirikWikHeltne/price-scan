import { getSupabase } from '@/lib/supabaseServer'
import { cacheHeaders } from '@/lib/cacheHeaders'
import { fetchAllRows } from '@/lib/fetchAllRows'

export const dynamic = 'force-dynamic'

export async function GET(request) {
  let supabase
  try {
    supabase = getSupabase()
  } catch {
    return Response.json({ error: 'Server misconfiguration: missing env vars' }, { status: 500 })
  }

  const { searchParams } = new URL(request.url)
  const kategori = searchParams.get('kategori')
  const search = searchParams.get('search')

  // Strip characters with special meaning in PostgREST filter syntax
  const safe = search ? search.replace(/[(),.\\*"%_]/g, '') : ''

  const startedAt = performance.now()
  const { data, error } = await fetchAllRows(() => {
    let query = supabase
      .from('prissammenligning')
      .select('*', { count: 'exact' })
      .order('kategori')
      .order('merke')
      .order('id')

    if (kategori && kategori !== 'alle') {
      query = query.eq('kategori', kategori)
    }
    if (safe) {
      query = query.or(`produkt.ilike.%${safe}%,merke.ilike.%${safe}%,varenummer.ilike.%${safe}%`)
    }
    return query
  })

  if (error) {
    console.error('Supabase error:', error)
    return Response.json({ error: 'Failed to fetch data' }, { status: 500 })
  }
  return Response.json(data, { headers: cacheHeaders(startedAt) })
}
