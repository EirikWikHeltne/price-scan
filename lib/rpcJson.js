import { getSupabase } from '@/lib/supabaseServer'
import { cacheHeaders } from '@/lib/cacheHeaders'
import { parseDager } from '@/lib/parseDager'

// Svarer med resultatet av en databasefunksjon som tar ?dager= og returnerer
// ferdig aggregert JSON. Aggregeringen gjøres i Postgres, slik at vi henter
// noen hundre rader i ett kall i stedet for å bla gjennom hele prishistorikken.
export async function respondWithRpc(request, fn, defaultDager) {
  let supabase
  try {
    supabase = getSupabase()
  } catch {
    return Response.json({ error: 'Server misconfiguration: missing env vars' }, { status: 500 })
  }

  const { searchParams } = new URL(request.url)
  const dager = parseDager(searchParams.get('dager'), defaultDager)

  const startedAt = performance.now()
  const { data, error } = await supabase.rpc(fn, { dager })

  if (error) {
    console.error('Supabase error:', error)
    // PGRST202: funksjonen finnes ikke — migreringen
    // supabase_migration_fast_reads.sql (price-scan) er ikke kjørt.
    const missing = error.code === 'PGRST202'
    return Response.json(
      { error: missing ? `Databasefunksjonen ${fn} mangler` : 'Failed to fetch data' },
      { status: 500, headers: { 'Cache-Control': 'no-store' } }
    )
  }

  return Response.json(Array.isArray(data) ? data : [], { headers: cacheHeaders(startedAt) })
}
