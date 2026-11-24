const PAGE_SIZE = 1000
const CONCURRENCY = 8

// Henter alle rader side for side. `buildQuery` skal returnere en NY spørring
// for hvert kall (Supabase-spørringer endres når man kaller .range() på dem,
// så samme objekt kan ikke brukes til flere sider samtidig).
//
// Spørringen må ha en entydig sortering (f.eks. avsluttet med .order('id'));
// uten det kan Postgres returnere radene i ulik rekkefølge fra side til side,
// slik at rader dupliseres eller mangler.
//
// Hvis spørringen er laget med select(..., { count: 'exact' }) vet vi etter
// første side hvor mange rader som finnes, og resten av sidene hentes
// parallelt. Uten antall hentes sidene én og én til en side ikke er full.
export async function fetchAllRows(buildQuery, { concurrency = CONCURRENCY } = {}) {
  const page = from => buildQuery().range(from, from + PAGE_SIZE - 1)

  const first = await page(0)
  if (first.error) return { data: null, error: first.error }
  const rows = first.data
  if (rows.length < PAGE_SIZE) return { data: rows, error: null }

  if (typeof first.count !== 'number') {
    for (let from = PAGE_SIZE; ; from += PAGE_SIZE) {
      const { data, error } = await page(from)
      if (error) return { data: null, error }
      for (const row of data) rows.push(row)
      if (data.length < PAGE_SIZE) break
    }
    return { data: rows, error: null }
  }

  const offsets = []
  for (let from = PAGE_SIZE; from < first.count; from += PAGE_SIZE) offsets.push(from)
  const pages = new Array(offsets.length)
  let next = 0
  let failure = null
  async function worker() {
    while (next < offsets.length && !failure) {
      const i = next++
      const { data, error } = await page(offsets[i])
      if (error) { failure = error; return }
      pages[i] = data
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, offsets.length) }, worker))
  if (failure) return { data: null, error: failure }

  for (const data of pages) for (const row of data) rows.push(row)
  return { data: rows, error: null }
}
