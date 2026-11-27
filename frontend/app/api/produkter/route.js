import { getSupabase } from '@/lib/supabaseServer'
import { cacheHeaders } from '@/lib/cacheHeaders'
import { fetchAllRows } from '@/lib/fetchAllRows'

export const dynamic = 'force-dynamic'

export async function GET() {
  let supabase
  try {
    supabase = getSupabase()
  } catch {
    return Response.json({ error: 'Server misconfiguration: missing env vars' }, { status: 500 })
  }

  const startedAt = performance.now()
  const load = columns => fetchAllRows(() => supabase
    .from('prissammenligning')
    .select(columns, { count: 'exact' })
    .order('kategori')
    .order('merke')
    .order('produkt')
    .order('id'))

  const BASE = 'id, produkt, merke, varenummer, kategori, sist_oppdatert'
  let { data, error } = await load(`${BASE}, niva1, niva2, niva3, segment`)
  // 42703: kolonnen finnes ikke — supabase_migration_category_tree.sql er
  // ikke kjørt ennå. Svar uten undernivåene i stedet for å feile.
  if (error?.code === '42703') {
    ;({ data, error } = await load(BASE))
  }

  if (error) {
    console.error('Supabase error:', error)
    return Response.json({ error: 'Failed to fetch data' }, { status: 500 })
  }

  return Response.json(data, { headers: cacheHeaders(startedAt) })
}
