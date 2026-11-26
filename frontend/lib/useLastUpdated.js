'use client'
import { useState, useEffect } from 'react'
import { fetchJson } from '@/lib/fetchJson'

/**
 * Henter dato for siste prisoppdatering fra /api/siste-oppdatering.
 * Hvis endepunktet ikke gir noen dato, utledes den fra nyeste
 * `sist_oppdatert` i `rows` (når tilgjengelig).
 */
export function useLastUpdated(rows) {
  const [lastUpdated, setLastUpdated] = useState(null)
  const [fromApi, setFromApi] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchJson('/api/siste-oppdatering')
      .then(json => {
        // Kan være både ren dato og fullt tidsstempel — behold bare datodelen
        const dato = typeof json?.dato === 'string' ? json.dato.slice(0, 10) : null
        if (cancelled || !dato) return
        // Midt på dagen for å unngå at tidssone-forskyvning flytter datoen
        const parsed = new Date(dato + 'T12:00:00')
        if (isNaN(parsed)) return
        setLastUpdated(parsed)
        setFromApi(true)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (fromApi || !rows?.length) return
    const dates = rows.map(r => r.sist_oppdatert).filter(Boolean).sort()
    if (!dates.length) return
    const parsed = new Date(dates[dates.length - 1])
    if (!isNaN(parsed)) setLastUpdated(parsed)
  }, [rows, fromApi])

  return lastUpdated
}
