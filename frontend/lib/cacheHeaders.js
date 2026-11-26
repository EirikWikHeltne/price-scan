// Prisdataene oppdateres én gang i døgnet, så svarene caches i Vercels CDN.
// De første 10 minuttene serveres svaret rett fra cachen. Etter det, og i
// inntil et døgn, får brukeren fortsatt det cachede svaret umiddelbart mens et
// nytt hentes i bakgrunnen — slik at ingen må vente på Supabase, heller ikke
// dagens første besøkende.
export const CACHE_HEADERS = {
  'Cache-Control': 'public, max-age=0, s-maxage=600, stale-while-revalidate=86400',
}

// Samme som over, pluss en Server-Timing-header som viser hvor lang tid
// databasekallene tok (synlig i nettleserens Network-fane).
export function cacheHeaders(startedAt) {
  return { ...CACHE_HEADERS, 'Server-Timing': `db;dur=${Math.round(performance.now() - startedAt)}` }
}
