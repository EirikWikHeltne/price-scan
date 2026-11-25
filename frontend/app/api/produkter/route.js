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
  const { data, error } = await fetchAllRows(() => supabase
    .from('prissammenligning')
    .select('id, produkt, merke, varenummer, kategori, sist_oppdatert', { count: 'exact' })
    .order('kategori')
    .order('merke')
    .order('produkt')
    .order('id'))

  if (error) {
    console.error('Supabase error:', error)
    return Response.json({ error: 'Failed to fetch data' }, { status: 500 })
  }

  return Response.json(data, { headers: cacheHeaders(startedAt) })
}
