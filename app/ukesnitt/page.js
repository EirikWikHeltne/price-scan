'use client'
import { useState, useEffect, useMemo, useCallback, useDeferredValue, useRef } from 'react'
import Header from '@/components/Header'
import Footer from '@/components/Footer'
import { TableSkeleton } from '@/components/Skeleton'
import { fetchJson } from '@/lib/fetchJson'
import { deriveRetailers } from '@/lib/retailers'
import { fmt } from '@/lib/format'
import { useLastUpdated } from '@/lib/useLastUpdated'
import { weekMeta } from '@/lib/isoWeek'
import { matchesSearch } from '@/lib/search'

const WEEK_RANGES = [
  { label: '4 uker', value: 28 },
  { label: '8 uker', value: 56 },
  { label: '12 uker', value: 84 },
  { label: '26 uker', value: 182 },
  { label: 'Alt', value: 0 },
]

export default function UkesnittPage() {
  const [history, setHistory]   = useState([])
  const [products, setProducts] = useState([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)
  const [tableNotFound, setTableNotFound] = useState(false)

  const [search, setSearch]     = useState('')

  const deferredSearch = useDeferredValue(search)
  const [kategori, setKategori] = useState('alle')
  const [merke, setMerke]       = useState('alle')
  const [chain, setChain]       = useState(null)
  const [dager, setDager]       = useState(84)

  const lastUpdated = useLastUpdated(products)

  // Product metadata (kategori/merke/produkt) so filtering works even when the
  // history fallback omits those columns.
  useEffect(() => {
    fetchJson('/api/produkter')
      .then(d => setProducts(Array.isArray(d) ? d : []))
      .catch(() => setProducts([]))
  }, [])

  // Teller opp for hvert kall, slik at et tregt svar for en tidligere valgt
  // periode ikke overskriver svaret for den som er valgt nå.
  const requestId = useRef(0)

  const fetchHistory = useCallback(async () => {
    const id = ++requestId.current
    const isStale = () => id !== requestId.current
    setLoading(true)
    setError(null)
    setTableNotFound(false)
    try {
      const json = await fetchJson(`/api/historikk?dager=${dager}&gruppering=uke`)
      if (isStale()) return
      if (json?.code === 'TABLE_NOT_FOUND') {
        setTableNotFound(true)
        setHistory([])
      } else if (Array.isArray(json)) {
        setHistory(json)
      } else {
        setError(json?.error || 'Kunne ikke hente prishistorikk')
        setHistory([])
      }
    } catch {
      if (isStale()) return
      setError('Kunne ikke hente prishistorikk. Prøv igjen.')
      setHistory([])
    }
    setLoading(false)
  }, [dager])

  useEffect(() => { fetchHistory() }, [fetchHistory])

  const retailers = useMemo(() => deriveRetailers(history), [history])

  // Default the selected chain to the first retailer once data arrives, and keep
  // the selection valid if the available retailers change.
  useEffect(() => {
    if (!retailers.length) return
    setChain(prev => (prev && retailers.some(r => r.key === prev) ? prev : retailers[0].key))
  }, [retailers])

  // Lookup of product metadata by varenummer.
  const metaByVn = useMemo(() => {
    const m = {}
    products.forEach(p => { if (p.varenummer) m[p.varenummer] = p })
    return m
  }, [products])

  const categories = useMemo(() => {
    const set = new Set()
    products.forEach(p => { if (p.kategori) set.add(p.kategori) })
    history.forEach(r => { if (r.kategori) set.add(r.kategori) })
    return [...set].sort((a, b) => a.localeCompare(b))
  }, [products, history])

  const brands = useMemo(() => {
    const set = new Set()
    products.forEach(p => { if (p.merke) set.add(p.merke) })
    history.forEach(r => { if (r.merke) set.add(r.merke) })
    return [...set].sort((a, b) => a.localeCompare(b))
  }, [products, history])

  // Aggregate into product × week × retailer averages.
  // products: { [vn]: { vn, produkt, merke, kategori, weeks: { [weekKey]: { [retailerKey]: { sum, count } } } } }
  const { weeks, rows } = useMemo(() => {
    if (!history.length || !retailers.length) return { weeks: [], rows: [] }

    const weekMetaByKey = {}
    const agg = {}

    history.forEach(row => {
      const dateStr = (row.dato || row.sist_oppdatert || '').slice(0, 10)
      if (!dateStr) return
      const wm = weekMeta(dateStr)
      if (!wm) return
      weekMetaByKey[wm.key] = wm

      const vn = row.varenummer || row.produkt
      if (!vn) return
      const meta = metaByVn[vn] || {}
      if (!agg[vn]) {
        agg[vn] = {
          vn,
          produkt: row.produkt || meta.produkt || vn,
          merke: row.merke || meta.merke || '',
          kategori: row.kategori || meta.kategori || '',
          weeks: {},
        }
      }
      const wk = agg[vn].weeks[wm.key] || (agg[vn].weeks[wm.key] = {})
      retailers.forEach(r => {
        const v = row[r.key]
        if (v == null || v === '' || isNaN(Number(v))) return
        const cell = wk[r.key] || (wk[r.key] = { sum: 0, count: 0 })
        cell.sum += Number(v)
        cell.count += 1
      })
    })

    const weekList = Object.values(weekMetaByKey).sort((a, b) => b.key.localeCompare(a.key))
    return { weeks: weekList, rows: Object.values(agg) }
  }, [history, retailers, metaByVn])

  // Rows for the currently selected chain, with the average computed per week.
  const chainRows = useMemo(() => {
    if (!chain) return []
    return rows
      .map(p => {
        const values = {}
        let hasAny = false
        weeks.forEach(w => {
          const cell = p.weeks[w.key]?.[chain]
          if (cell && cell.count) {
            values[w.key] = +(cell.sum / cell.count).toFixed(2)
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
            <button className="tab active" style={{ marginTop: '1rem' }} onClick={fetchHistory}>
              Prøv igjen
            </button>
          </div>
        ) : tableNotFound ? (
          <div className="empty">
            <div className="empty-icon">&#128202;</div>
            <div className="empty-text">Prishistorikk er ikke tilgjengelig ennå</div>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '0.5rem' }}>
              Ukentlige snittpriser vises her når historiske data er tilgjengelig.
            </p>
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
