import { getSupabase } from '@/lib/supabaseServer'
import { CACHE_HEADERS } from '@/lib/cacheHeaders'

export const dynamic = 'force-dynamic'

export async function GET() {
  let supabase
  try {
    supabase = getSupabase()
  } catch {
    return Response.json({ error: 'Server misconfiguration' }, { status: 500 })
  }

  // Nyeste skanning leses rett fra priser-tabellen, der scraped_at er
  // indeksert. Visningen prishistorikk kan ikke bruke indeksen når den
  // sorteres på dato, og måtte sortere hele prishistorikken for ett svar.
  const { data, error } = await supabase
    .from('priser')
    .select('scraped_at')
    .order('scraped_at', { ascending: false })
    .limit(1)

  if (error) console.error('Supabase error:', error)

  const dato = data?.[0]?.scraped_at?.slice(0, 10) ?? null
  return Response.json({ dato }, { headers: CACHE_HEADERS })
}
