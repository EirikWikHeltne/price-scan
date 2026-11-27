'use client'
import { useState, useEffect, useMemo, useCallback, useDeferredValue } from 'react'
import dynamic from 'next/dynamic'
import Header from '@/components/Header'
import Footer from '@/components/Footer'
import { TableSkeleton, ChartSkeleton } from '@/components/Skeleton'
import { deriveRetailers } from '@/lib/retailers'
import { fmt } from '@/lib/format'
import CategoryFilter from '@/components/CategoryFilter'
import ShowMore, { ROW_STEP } from '@/components/ShowMore'
import { CAT_CLASS, NO_FILTER, matchesLevels, categoryPath } from '@/lib/categories'
import { useLastUpdated } from '@/lib/useLastUpdated'
import { fetchJson } from '@/lib/fetchJson'
import { matchesSearch } from '@/lib/search'
import { compareValues } from '@/lib/sort'

const HomeCharts = dynamic(() => import('@/components/HomeCharts'), {
  ssr: false,
  loading: () => <ChartSkeleton />,
})

export default function Page() {
  const [data, setData]         = useState([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)
  const [search, setSearch]     = useState('')
  const [cat, setCat]           = useState(NO_FILTER)
  const [rowLimit, setRowLimit] = useState(ROW_STEP)
  const [merke, setMerke]       = useState('alle')
  const [sortCol, setSortCol]   = useState('merke')
  const [sortDir, setSortDir]   = useState('asc')
  const [showGraphs, setShowGraphs]   = useState(true)

  const lastUpdated = useLastUpdated(data)

  // Hele pristabellen er liten nok til å hentes én gang; kategori og søk
  // filtreres lokalt slik at bytte av fane og skriving i søkefeltet er
  // umiddelbart, uten nytt serverkall og spinner.
  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const json = await fetchJson('/api/priser')
      setData(Array.isArray(json) ? json : [])
    } catch(e) {
      console.error(e)
      setError('Kunne ikke hente priser. Prøv igjen.')
      setData([])
    }
    setLoading(false)
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const deferredSearch = useDeferredValue(search)

  const retailers = useMemo(() => deriveRetailers(data), [data])

  // Rader etter kategori + søk (det serveren tidligere filtrerte på)
  const filtered = useMemo(() => {
    let d = data
    d = d.filter(r => matchesLevels(r, cat))
    if (deferredSearch.trim()) d = d.filter(r => matchesSearch(r, deferredSearch))
    return d
  }, [data, cat, deferredSearch])

  const brands = useMemo(() => {
    if (!filtered.length) return []
    return [...new Set(filtered.map(r => r.merke).filter(Boolean))].sort((a, b) => a.localeCompare(b))
  }, [filtered])

  // Valgt merke kan forsvinne fra listen når kategori eller søk endres. Da skal
  // filteret ikke lenger gjelde, ellers blir tabellen tom mens nedtrekkslisten
  // viser «Alle merker».
  const activeMerke = brands.includes(merke) ? merke : 'alle'

  const visible = useMemo(
    () => (activeMerke === 'alle' ? filtered : filtered.filter(r => r.merke === activeMerke)),
    [filtered, activeMerke]
  )

  const sorted = useMemo(() => {
    if (!visible.length) return []
    return [...visible].sort((a, b) => compareValues(a[sortCol], b[sortCol], sortDir))
  }, [visible, sortCol, sortDir])

  const stats = useMemo(() => {
    if (!filtered.length) return {}
    const withPrices = filtered.filter(r => r.laveste_pris)
    const avgLow = withPrices.reduce((s,r) => s + Number(r.laveste_pris), 0) / (withPrices.length || 1)
    const avgHigh = withPrices.reduce((s,r) => s + Number(r.hoyeste_pris), 0) / (withPrices.length || 1)
    const coverage = retailers.map(r => ({
      ...r,
      count: filtered.filter(row => row[r.key] !== null && row[r.key] !== undefined).length
    }))
    return { avgLow, avgHigh, coverage, total: filtered.length }
  }, [filtered, retailers])

  function handleSort(col) {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(col); setSortDir('asc') }
  }

  const renderSortIcon = (col) => {
    if (sortCol !== col) return <span style={{opacity:0.3}}>↕</span>
    return <span>{sortDir === 'asc' ? '↑' : '↓'}</span>
  }

  async function downloadExcel() {
    // Lazy-load xlsx så det store biblioteket holdes ute av siden til det trengs
    const XLSX = await import('xlsx')
    const rows = sorted.map(row => {
      const prices = retailers.map(r => row[r.key]).filter(v => v != null)
      const min = prices.length ? Math.min(...prices) : null
      const max = prices.length ? Math.max(...prices) : null
      const obj = {
        Produkt: row.produkt,
        Merke: row.merke,
        Varenummer: row.varenummer,
        Kategori: row.kategori,
        'Nivå 1': row.niva1 ?? null,
        'Nivå 2': row.niva2 ?? null,
        'Nivå 3': row.niva3 ?? null,
      }
      retailers.forEach(r => { obj[r.label] = row[r.key] ?? null })
      obj['Laveste pris'] = min
      obj['Høyeste pris'] = max
      obj['Spread'] = min != null && max != null ? max - min : null
      return obj
    })
    const ws = XLSX.utils.json_to_sheet(rows)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Priser')
    XLSX.writeFile(wb, `karo-priser-${new Date().toISOString().slice(0, 10)}.xlsx`)
  }

  return (
    <div className="app">
      <Header active="/" lastUpdated={lastUpdated} />

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
        <CategoryFilter rows={data} value={cat} onChange={setCat} />
        <select
          className="brand-select"
          aria-label="Merke"
          value={activeMerke}
          onChange={e => setMerke(e.target.value)}
        >
          <option value="alle">Alle merker</option>
          {brands.map(b => <option key={b} value={b}>{b}</option>)}
        </select>
        <div className="controls-right">
          <span className="count-badge">{sorted.length} produkter</span>
          <button
            className={`tab tab-toggle ${showGraphs ? 'active' : ''}`}
            onClick={() => setShowGraphs(!showGraphs)}
            aria-pressed={showGraphs}
          >
            {showGraphs ? 'Skjul grafer' : 'Vis grafer'}
          </button>
          <button
            className="btn-excel"
            onClick={downloadExcel}
            disabled={!sorted.length}
          >
            Last ned Excel
          </button>
        </div>
      </div>

      {!loading && stats.total > 0 && (
        <div className="stats-bar">
          <div className="stat">
            <span className="stat-label">Produkter</span>
            <span className="stat-value">{stats.total}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Snitt laveste pris</span>
            <span className="stat-value">{fmt(stats.avgLow)} kr</span>
          </div>
          <div className="stat">
            <span className="stat-label">Snitt høyeste pris</span>
            <span className="stat-value">{fmt(stats.avgHigh)} kr</span>
          </div>
          {stats.coverage?.map(r => (
            <div key={r.key} className="stat">
              <span className="stat-label" style={{color: r.color}}>{r.label}</span>
              <span className="stat-value">{r.count}</span>
              <span className="stat-sub">produkter med pris</span>
            </div>
          ))}
        </div>
      )}

      {/* Summary Graphs */}
      {showGraphs && loading && <ChartSkeleton />}
      {showGraphs && !loading && visible.length > 0 && (
        <HomeCharts visible={visible} retailers={retailers} />
      )}

      <div className="table-wrap">
        {loading ? (
          <TableSkeleton cols={7} label="Henter priser..." />
        ) : error ? (
          <div className="empty">
            <div className="empty-icon">&#9888;</div>
            <div className="empty-text">{error}</div>
            <button className="tab active" style={{ marginTop: '1rem' }} onClick={loadData}>
              Prøv igjen
            </button>
          </div>
        ) : sorted.length === 0 ? (
          <div className="empty">
            <div className="empty-icon">&#9678;</div>
            <div className="empty-text">Ingen produkter funnet</div>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th onClick={() => handleSort('produkt')} className={sortCol==='produkt'?'sorted':''}>
                  Produkt {renderSortIcon('produkt')}
                </th>
                <th onClick={() => handleSort('kategori')} className={`th-category ${sortCol==='kategori'?'sorted':''}`}>
                  Kategori {renderSortIcon('kategori')}
                </th>
                {retailers.map(r => (
                  <th key={r.key} onClick={() => handleSort(r.key)} className={`th-price ${sortCol===r.key?'sorted':''}`} style={{textAlign:'right'}}>
                    <div className="retailer-header" style={{justifyContent:'flex-end'}}>
                      <span className="retailer-dot" style={{background: r.color}}></span>
                      <span className="retailer-label">{r.label}</span> {renderSortIcon(r.key)}
                    </div>
                  </th>
                ))}
                <th onClick={() => handleSort('laveste_pris')} className={sortCol==='laveste_pris'?'sorted':''} style={{textAlign:'right'}}>
                  Lavest {renderSortIcon('laveste_pris')}
                </th>
                <th style={{textAlign:'right'}}>Spread</th>
              </tr>
            </thead>
            <tbody>
              {sorted.slice(0, rowLimit).map(row => {
                const prices = retailers.map(r => row[r.key]).filter(v => v !== null && v !== undefined)
                const min = prices.length ? Math.min(...prices) : null
                const max = prices.length ? Math.max(...prices) : null
                const spread = min != null && max != null ? max - min : null

                return (
                  <tr key={row.id}>
                    <td className="td-product">
                      <div className="product-name">{row.produkt}</div>
                      <div className="product-brand">{row.merke}</div>
                      <div className="product-vn">{row.varenummer}</div>
                    </td>
                    <td className="td-category">
                      <span className={`cat-pill ${CAT_CLASS[row.kategori] || ''}`}>
                        {row.kategori}
                      </span>
                      {categoryPath(row) && <div className="cat-path">{categoryPath(row)}</div>}
                    </td>
                    {retailers.map(r => {
                      const val = row[r.key]
                      const isMin = val !== null && val !== undefined && val === min && prices.length > 1
                      const isMax = val !== null && val !== undefined && val === max && prices.length > 1 && min !== max
                      return (
                        <td key={r.key} className="td-price" data-label={r.label}>
                          {val === null || val === undefined ? (
                            <span className="price-null">—</span>
                          ) : (
                            <span className={`price-val ${isMin ? 'price-lowest' : isMax ? 'price-highest' : ''}`}>
                              {fmt(val)}
                              {isMin && <span className="price-dot" style={{background:'#1D6A3A'}}></span>}
                            </span>
                          )}
                        </td>
                      )
                    })}
                    <td className="td-price" data-label="Lavest">
                      {min != null ? (
                        <span className="price-val price-lowest">{fmt(min)}</span>
                      ) : <span className="price-null">—</span>}
                    </td>
                    <td className="td-diff" data-label="Spread">
                      {spread != null && spread > 0 ? (
                        <span className="diff-val diff-pos">+{fmt(spread)}</span>
                      ) : spread === 0 ? (
                        <span className="diff-val diff-zero">—</span>
                      ) : (
                        <span className="price-null">—</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
        {!loading && !error && (
          <ShowMore
            shown={Math.min(rowLimit, sorted.length)}
            total={sorted.length}
            onMore={() => setRowLimit(n => n + ROW_STEP)}
            onAll={() => setRowLimit(Infinity)}
          />
        )}
      </div>

      <Footer />
    </div>
  )
}
