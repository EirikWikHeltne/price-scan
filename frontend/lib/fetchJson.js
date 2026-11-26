'use client'

// Enkel klient-side cache for API-kall. Prisdataene oppdateres én gang i døgnet,
// så det er ingen grunn til å hente hele pristabellen på nytt hver gang man
// bytter fane. Samtidige kall til samme URL deler ett nettverkskall.
const TTL_MS = 5 * 60 * 1000
const cache = new Map() // url -> { promise, time }

export function fetchJson(url) {
  const hit = cache.get(url)
  if (hit && Date.now() - hit.time < TTL_MS) return hit.promise

  const promise = fetch(url).then(async res => {
    const json = await res.json().catch(() => null)
    // Ikke cache feil — neste forsøk skal gå mot serveren igjen
    if (!res.ok && !json?.code) {
      const err = new Error(`Server error: ${res.status}`)
      err.status = res.status
      throw err
    }
    return json
  })
  const entry = { promise, time: Date.now() }
  promise.catch(() => { if (cache.get(url) === entry) cache.delete(url) })
  cache.set(url, entry)
  return promise
}
