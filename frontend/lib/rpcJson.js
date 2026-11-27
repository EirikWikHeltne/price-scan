import { getSupabase } from '@/lib/supabaseServer'
import { cacheHeaders } from '@/lib/cacheHeaders'
import { parseDager } from '@/lib/parseDager'
import { branchArgs } from '@/lib/branchArgs'

// Svarer med resultatet av en databasefunksjon som tar ?dager= (og eventuelt
// en gren av kategoritreet) og returnerer ferdig aggregert JSON.
// Aggregeringen gjøres i Postgres, slik at vi henter noen hundre rader i ett
// kall i stedet for å bla gjennom hele prishistorikken.
//
// `unfilteredFallback`: hvis databasen ikke har funksjonen med gren-
// argumentene ennå (supabase_migration_category_tree.sql er ikke kjørt),
// svar med hele resultatet i stedet for en feil. Bare for sider som selv
// filtrerer radene på kategori.
export async function respondWithRpc(request, fn, defaultDager, { unfilteredFallback = false } = {}) {
  let supabase
  try {
    supabase = getSupabase()
  } catch {
    return Response.json({ error: 'Server misconfiguration: missing env vars' }, { status: 500 })
  }

  const { searchParams } = new URL(request.url)
  const dager = parseDager(searchParams.get('dager'), defaultDager)
  const branch = branchArgs(searchParams)

  const startedAt = performance.now()
  let { data, error } = await supabase.rpc(fn, { dager, ...branch })
  // PGRST202: ingen funksjon med dette navnet og disse argumentene.
  if (error?.code === 'PGRST202' && unfilteredFallback && Object.keys(branch).length) {
    ;({ data, error } = await supabase.rpc(fn, { dager }))
  }

  if (error) {
    console.error('Supabase error:', error)
    const missing = error.code === 'PGRST202'
    return Response.json(
      { error: missing ? `Databasefunksjonen ${fn} mangler eller er utdatert. Kjør SQL-migreringene i rotmappen.` : 'Failed to fetch data' },
      { status: 500, headers: { 'Cache-Control': 'no-store' } }
    )
  }

  return Response.json(Array.isArray(data) ? data : [], { headers: cacheHeaders(startedAt) })
}
