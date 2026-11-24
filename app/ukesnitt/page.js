'use client'
import { useState, useEffect, useMemo, useCallback, useDeferredValue, useRef } from 'react'
import Header from '@/components/Header'
import Footer from '@/components/Footer'
import { TableSkeleton } from '@/components/Skeleton'
import { fetchJson } from '@/lib/fetchJson'
import { fmt } from '@/lib/format'
import { useLastUpdated } from '@/lib/useLastUpdated'
import { buildWeekly } from '@/lib/ukesnitt'
import { matchesSearch } from '@/lib/search'

const WEEK_RANGES = [
  { label: '4 uker', value: 28 },
  { label: '8 uker', value: 56 },
  { label: '12 uker', value: 84 },
  { label: '26 uker', value: 182 },
  { label: 'Alt', value: 0 },
]

export default function UkesnittPage() {
  const [data, setData]         = useState([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)

  const [search, setSearch]     = useState('')

  const deferredSearch = useDeferredValue(search)
  const [kategori, setKategori] = useState('alle')
  const [merke, setMerke]       = useState('alle')
  const [chain, setChain]       = useState(null)
  const [dager, setDager]       = useState(84)

  const lastUpdated = useLastUpdated()

  // Teller opp for hvert kall, slik at et tregt svar for en tidligere valgt
  // periode ikke overskriver svaret for den som er valgt nå.
  const requestId = useRef(0)

  // Ukesnittene regnes ut i databasen; svaret er én rad per produkt.
  const fetchWeekly = useCallback(async () => {
    const id = ++requestId.current
    const isStale = () => id !== requestId.current
    setLoading(true)
    setError(null)
    try {
      const json = await fetchJson(`/api/ukesnitt?dager=${dager}`)
      if (isStale()) return
      if (Array.isArray(json)) {
        setData(json)
      } else {
        setError(json?.error || 'Kunne ikke hente prishistorikk')
        setData([])
      }
    } catch {
      if (isStale()) return
      setError('Kunne ikke hente prishistorikk. Prøv igjen.')
      setData([])
    }
    setLoading(false)
  }, [dager])

  useEffect(() => { fetchWeekly() }, [fetchWeekly])

  const { weeks, rows, retailers } = useMemo(() => buildWeekly(data), [data])

  // Default the selected chain to the first retailer once data arrives, and keep
  // the selection valid if the available retailers change.
  useEffect(() => {
    if (!retailers.length) return
    setChain(prev => (prev && retailers.some(r => r.key === prev) ? prev : retailers[0].key))
  }, [retailers])

  const categories = useMemo(() => {
    const set = new Set()
    rows.forEach(r => { if (r.kategori) set.add(r.kategori) })
    return [...set].sort((a, b) => a.localeCompare(b))
  }, [rows])

  const brands = useMemo(() => {
    const set = new Set()
    rows.forEach(r => { if (r.merke) set.add(r.merke) })
    return [...set].sort((a, b) => a.localeCompare(b))
  }, [rows])

  // Rows for the currently selected chain, with the average computed per week.
  const chainRows = useMemo(() => {
    if (!chain) return []
    return rows
      .map(p => {
        const values = {}
        let hasAny = false
        weeks.forEach(w => {
          const v = p.weeks[w.key]?.[chain]
          if (v != null) {
            values[w.key] = v
            hasAny = true
          }
        })
        return { ...p, values, hasAny }
      })
      .filter(p => p.hasAny)
      .filter(p => kategori === 'alle' || p.kategori === kategori)
      .filter(p => merke === 'alle' || p.merke === merke)
      .filter(p => matchesSearch({ ...p, varenummer: p.vn }, deferredSearch))
      .sort((a, b) => (a.produkt || '').localeCompare(b.produkt || ''))
  }, [rows, weeks, chain, kategori, merke, deferredSearch])

  const chainLabel = retailers.find(r => r.key === chain)?.label || ''

  async function downloadExcel() {
    const XLSX = await import('xlsx')
    const out = chainRows.map(p => {
      const obj = {
        Produkt: p.produkt,
        Merke: p.merke,
        Varenummer: p.vn,
        Kategori: p.kategori,
      }
      weeks.forEach(w => { obj[`Uke ${w.week} (${w.year})`] = p.values[w.key] ?? null })
      return obj
    })
    const ws = XLSX.utils.json_to_sheet(out)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, `Ukesnitt ${chainLabel}`.slice(0, 31))
    XLSX.writeFile(wb, `karo-ukesnitt-${chain}-${new Date().toISOString().slice(0, 10)}.xlsx`)
  }

  return (
    <div className="app">
      <Header active="/ukesnitt" lastUpdated={lastUpdated} />

      <div className="controls">
        <div className="search-wrap">
          <span className="search-icon">&#x1F50D;</span>
          <input
            className="search-input"
            type="search"
            aria-label="Søk"
            placeholder="Søk produkt, merke, varenr..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="filter-tabs">
          {['alle', ...categories].map(k => (
            <button
              key={k}
              className={`tab ${kategori === k ? 'active' : ''}`}
              onClick={() => setKategori(k)}
            >
              {k === 'alle' ? 'Alle kategorier' : k}
            </button>
          ))}
        </div>
        <select
          className="brand-select"
          aria-label="Merke"
          value={merke}
          onChange={e => setMerke(e.target.value)}
        >
          <option value="alle">Alle merker</option>
          {brands.map(b => <option key={b} value={b}>{b}</option>)}
        </select>
        <div className="controls-right">
          <span className="count-badge">{chainRows.length} produkter</span>
          <button
            className="btn-excel"
            onClick={downloadExcel}
            disabled={!chainRows.length}
          >
            Last ned Excel
          </button>
        </div>
      </div>

      {/* Chain + week-range selectors */}
      <div className="time-filter-bar">
        <span className="time-filter-label">Apotek:</span>
        <div className="filter-tabs">
          {retailers.map(r => (
            <button
              key={r.key}
              className={`tab ${chain === r.key ? 'active' : ''}`}
              onClick={() => setChain(r.key)}
            >
              <span className="retailer-dot" style={{ background: r.color, marginRight: '0.4rem' }}></span>
              {r.label}
            </button>
          ))}
        </div>
        <div className="filter-tabs" style={{ marginLeft: 'auto' }}>
          {WEEK_RANGES.map(w => (
            <button
              key={w.value}
              className={`tab ${dager === w.value ? 'active' : ''}`}
              onClick={() => setDager(w.value)}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>

      <div className="table-wrap" style={{ overflowX: 'auto' }}>
        {loading ? (
          <TableSkeleton cols={9} label="Henter ukesnitt..." />
        ) : error ? (
          <div className="empty">
            <div className="empty-icon">&#9888;</div>
            <div className="empty-text">{error}</div>
            <button className="tab active" style={{ marginTop: '1rem' }} onClick={fetchWeekly}>
              Prøv igjen
            </button>
          </div>
        ) : chainRows.length === 0 || weeks.length === 0 ? (
          <div className="empty">
            <div className="empty-icon">&#9678;</div>
            <div className="empty-text">Ingen data for {chainLabel || 'valgt apotek'} i perioden</div>
          </div>
        ) : (
          <table className="ukesnitt-table">
            <thead>
              <tr>
                <th className="ukesnitt-prodcol">Produkt</th>
                {weeks.map(w => (
                  <th key={w.key} style={{ textAlign: 'right' }} title={`Uke starter ${w.monday}`}>
                    <div className="ukesnitt-weekhead">
                      <span className="ukesnitt-weeknum">Uke {w.week}</span>
                      <span className="ukesnitt-weekyear">{w.year}</span>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {chainRows.map(p => (
                <tr key={p.vn}>
                  <td className="td-product ukesnitt-prodcol">
                    <div className="product-name">{p.produkt}</div>
                    <div className="product-brand">{p.merke}</div>
                    <div className="product-vn">{p.vn}</div>
                  </td>
                  {weeks.map((w, i) => {
                    const val = p.values[w.key]
                    // Compare against the next older week that has a value.
                    let delta = null
                    for (let j = i + 1; j < weeks.length; j++) {
                      const prev = p.values[weeks[j].key]
                      if (prev != null && val != null) { delta = val - prev; break }
                      if (prev != null) break
                    }
                    return (
                      <td key={w.key} className="td-price" data-label={`Uke ${w.week}`}>
                        {val == null ? (
                          <span className="price-null">—</span>
                        ) : (
                          <span className="ukesnitt-cell">
                            <span className="price-val">{fmt(val)}</span>
                            {delta != null && delta !== 0 && (
                              <span className={`ukesnitt-delta ${delta < 0 ? 'down' : 'up'}`}>
                                {delta < 0 ? '▼' : '▲'} {fmt(Math.abs(delta))}
                              </span>
                            )}
                          </span>
                        )}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Footer left="Karo Healthcare Norway" />
    </div>
  )
}
