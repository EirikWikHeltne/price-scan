'use client'
import { useState, useEffect, useMemo, useDeferredValue } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts'
import { CHART_ANIM } from '@/lib/chartTheme'
import Header from '@/components/Header'
import Footer from '@/components/Footer'
import { TableSkeleton } from '@/components/Skeleton'
import { fetchJson } from '@/lib/fetchJson'
import { matchesSearch } from '@/lib/search'
import { compareValues } from '@/lib/sort'
import { deriveRetailers } from '@/lib/retailers'
import { fmt } from '@/lib/format'
import { useLastUpdated } from '@/lib/useLastUpdated'

// "Solpleie" dekker solkrem, after sun og beslektede kategorier. Vi matcher
// alle kategorier som inneholder "sol" eller "sun" (norsk + engelsk) slik at
// kartet fanger opp ulike kategorinavn automatisk.
function isSunCare(kategori) {
  return typeof kategori === 'string' && /sol|sun/i.test(kategori)
}

// Beregn nøkkeltall per SKU på tvers av kjedene.
function analyzeRow(row, retailers) {
  const prices = retailers
    .map(r => row[r.key])
    .filter(v => v !== null && v !== undefined)
    .map(Number)
  if (!prices.length) {
    return { min: null, max: null, avg: null, spread: null, spreadPct: null, cheapest: null }
  }
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const avg = prices.reduce((s, v) => s + v, 0) / prices.length
  const spread = max - min
  const spreadPct = min > 0 ? (spread / min) * 100 : 0
  const cheapest = prices.length > 1
    ? retailers.find(r => row[r.key] != null && Number(row[r.key]) === min) || null
    : null
  return { min, max, avg, spread, spreadPct, cheapest }
}

function ProductAvgTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{p.fullName}</div>
      <div className="chart-tooltip-row">Snittpris: {fmt(p.avg)} kr</div>
      {p.min != null && (
        <div className="chart-tooltip-row">Lavest–høyest: {fmt(p.min)}–{fmt(p.max)} kr</div>
      )}
    </div>
  )
}

const MAX_CHART_BARS = 40

export default function SolpleiePage() {
  const [data, setData]       = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)
  const [search, setSearch]   = useState('')
  const deferredSearch = useDeferredValue(search)
  const [merke, setMerke]     = useState('alle')
  const [scope, setScope]     = useState('solpleie') // 'solpleie' | 'alle'
  const [sortCol, setSortCol] = useState('snitt')
  const [sortDir, setSortDir] = useState('desc')

  const lastUpdated = useLastUpdated(data)

  useEffect(() => {
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const json = await fetchJson('/api/priser')
        setData(Array.isArray(json) ? json : [])
      } catch (e) {
        console.error(e)
        setError('Kunne ikke hente priser. Prøv igjen.')
        setData([])
      }
      setLoading(false)
    }
    load()
  }, [])

  // Finnes det i det hele tatt solpleie-kategorier i datagrunnlaget?
  const hasSunCare = useMemo(() => data.some(r => isSunCare(r.kategori)), [data])

  // Velg produktgrunnlag ut fra scope. Faller automatisk tilbake til alle
  // produkter dersom det ikke finnes noen solpleie-kategori i dataene, slik at
  // siden aldri blir stående tom.
  const baseProducts = useMemo(() => {
    if (scope === 'solpleie' && hasSunCare) return data.filter(r => isSunCare(r.kategori))
    return data
  }, [data, scope, hasSunCare])

  const retailers = useMemo(() => deriveRetailers(baseProducts), [baseProducts])

  const brands = useMemo(() => {
    return [...new Set(baseProducts.map(r => r.merke).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b))
  }, [baseProducts])

  // Valgt merke finnes kanskje ikke lenger når utvalget (scope) byttes
  const activeMerke = brands.includes(merke) ? merke : 'alle'

  // Berik hver rad med analysefelter
  const enriched = useMemo(() => {
    return baseProducts.map(row => ({ ...row, _calc: analyzeRow(row, retailers) }))
  }, [baseProducts, retailers])

  const filtered = useMemo(() => {
    let d = enriched
    if (activeMerke !== 'alle') d = d.filter(r => r.merke === activeMerke)
    if (deferredSearch.trim()) d = d.filter(r => matchesSearch(r, deferredSearch))
    const calcCols = { laveste: 'min', hoyeste: 'max', snitt: 'avg', spread: 'spread', spreadPct: 'spreadPct' }
    return [...d].sort((a, b) => {
      let av, bv
      if (calcCols[sortCol]) {
        av = a._calc[calcCols[sortCol]]
        bv = b._calc[calcCols[sortCol]]
      } else {
        av = a[sortCol]; bv = b[sortCol]
      }
      return compareValues(av, bv, sortDir)
    })
  }, [enriched, activeMerke, deferredSearch, sortCol, sortDir])

  // Data for snittpris-grafen: ett produkt per stolpe, sortert på snittpris.
  const avgChartData = useMemo(() => {
    const withAvg = filtered
      .filter(r => r._calc.avg != null)
      .map(r => ({
        fullName: r.produkt,
        name: (r.produkt || '').length > 32 ? r.produkt.slice(0, 32) + '…' : (r.produkt || ''),
        avg: +r._calc.avg.toFixed(2),
        min: r._calc.min,
        max: r._calc.max,
        color: r._calc.cheapest?.color || 'var(--accent)',
      }))
      .sort((a, b) => b.avg - a.avg)
    return { rows: withAvg.slice(0, MAX_CHART_BARS), total: withAvg.length }
  }, [filtered])

  // Nøkkeltall for utvalget
  const stats = useMemo(() => {
    if (!filtered.length) return null
    const withPrices = filtered.filter(r => r._calc.min != null)
    const avgPrice = withPrices.length
      ? withPrices.reduce((s, r) => s + r._calc.avg, 0) / withPrices.length : 0
    const avgLow = withPrices.length
      ? withPrices.reduce((s, r) => s + r._calc.min, 0) / withPrices.length : 0
    const spreads = withPrices.filter(r => r._calc.spread != null).map(r => r._calc.spread)
    const avgSpread = spreads.length ? spreads.reduce((s, v) => s + v, 0) / spreads.length : 0

    const cheapestCounts = {}
    retailers.forEach(r => { cheapestCounts[r.key] = 0 })
    withPrices.forEach(r => { if (r._calc.cheapest) cheapestCounts[r._calc.cheapest.key]++ })
    let topCheapest = null, topCount = 0
    retailers.forEach(r => {
      if (cheapestCounts[r.key] > topCount) { topCount = cheapestCounts[r.key]; topCheapest = r }
    })

    const coverage = retailers.map(r => ({
      ...r,
      count: filtered.filter(row => row[r.key] !== null && row[r.key] !== undefined).length,
    }))

    return { skus: filtered.length, avgPrice, avgLow, avgSpread, topCheapest, topCount, coverage }
  }, [filtered, retailers])

  function handleSort(col) {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(col); setSortDir(col === 'produkt' || col === 'varenummer' ? 'asc' : 'desc') }
  }

  const renderSortIcon = (col) => {
    if (sortCol !== col) return <span style={{ opacity: 0.3 }}>↕</span>
    return <span>{sortDir === 'asc' ? '↑' : '↓'}</span>
  }

  const scopeLabel = scope === 'solpleie' && hasSunCare ? 'solpleie' : 'alle produkter'

  async function downloadExcel() {
    // Lazy-load xlsx så det store biblioteket holdes ute av siden til det trengs
    const XLSX = await import('xlsx')
    const priskart = filtered.map(row => {
      const c = row._calc
      const obj = {
        Varenummer: row.varenummer,
        Produkt: row.produkt,
        Merke: row.merke,
        Kategori: row.kategori,
      }
      retailers.forEach(r => { obj[r.label] = row[r.key] ?? null })
      obj['Laveste pris'] = c.min
      obj['Høyeste pris'] = c.max
      obj['Snittpris'] = c.avg != null ? +c.avg.toFixed(2) : null
      obj['Spread (kr)'] = c.spread
      obj['Spread (%)'] = c.spreadPct != null ? +c.spreadPct.toFixed(1) : null
      obj['Billigst kjede'] = c.cheapest?.label ?? null
      obj['Sist oppdatert'] = row.sist_oppdatert
        ? new Date(row.sist_oppdatert).toLocaleDateString('nb-NO')
        : ''
      return obj
    })

    const oppsummering = retailers.map(r => {
      const vals = filtered.map(row => row[r.key]).filter(v => v != null).map(Number)
      const billigst = filtered.filter(row => row._calc.cheapest?.key === r.key).length
      return {
        Kjede: r.label,
        'Antall SKU med pris': vals.length,
        'Snittpris': vals.length ? +(vals.reduce((s, v) => s + v, 0) / vals.length).toFixed(2) : null,
        'Laveste pris': vals.length ? Math.min(...vals) : null,
        'Høyeste pris': vals.length ? Math.max(...vals) : null,
        'Billigst (antall SKU)': billigst,
      }
    })

    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(priskart), 'Priskart per SKU')
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(oppsummering), 'Oppsummering per kjede')
    const tag = scope === 'solpleie' && hasSunCare ? 'solpleie' : 'alle'
    XLSX.writeFile(wb, `karo-${tag}-priskart-${new Date().toISOString().slice(0, 10)}.xlsx`)
  }

  return (
    <div className="app">
      <Header active="/solpleie" lastUpdated={lastUpdated} />

      <div className="compare-intro">
        <h2 className="compare-title">Priskart – Solpleie</h2>
        <p className="compare-desc">
          Prisoversikt per SKU på tvers av apotekkjedene, med graf for å sammenligne gjennomsnittspris. Last ned til Excel for videre analyse.
        </p>
      </div>

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
          <button
            className={`tab ${scope === 'solpleie' ? 'active' : ''}`}
            onClick={() => setScope('solpleie')}
            disabled={!hasSunCare}
            title={hasSunCare ? '' : 'Ingen solpleie-kategori funnet i dataene'}
          >
            Solpleie
          </button>
          <button
            className={`tab ${scope === 'alle' ? 'active' : ''}`}
            onClick={() => setScope('alle')}
          >
            Alle produkter
          </button>
        </div>
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
          <span className="count-badge">{filtered.length} SKU-er</span>
          <button
            className="btn-excel"
            onClick={downloadExcel}
            disabled={!filtered.length}
          >
            Last ned Excel
          </button>
        </div>
      </div>

      {scope === 'solpleie' && !hasSunCare && !loading && data.length > 0 && (
        <div className="time-filter-bar">
          <span className="time-filter-label" style={{ color: 'var(--amber, #B45309)' }}>
            Fant ingen egen solpleie-kategori i dataene – viser alle produkter. Gi beskjed om hva kategorien heter, så låser jeg kartet til den.
          </span>
        </div>
      )}

      {stats && !loading && (
        <div className="stats-bar">
          <div className="stat">
            <span className="stat-label">SKU-er</span>
            <span className="stat-value">{stats.skus}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Snittpris</span>
            <span className="stat-value">{fmt(stats.avgPrice)} kr</span>
          </div>
          <div className="stat">
            <span className="stat-label">Snitt laveste pris</span>
            <span className="stat-value">{fmt(stats.avgLow)} kr</span>
          </div>
          <div className="stat">
            <span className="stat-label">Snitt spread</span>
            <span className="stat-value">{fmt(stats.avgSpread)} kr</span>
          </div>
          {stats.topCheapest && (
            <div className="stat">
              <span className="stat-label">Billigst oftest</span>
              <span className="stat-value" style={{ color: stats.topCheapest.color }}>{stats.topCheapest.label}</span>
              <span className="stat-sub">{stats.topCount} av {stats.skus} SKU-er</span>
            </div>
          )}
          {stats.coverage?.map(r => (
            <div key={r.key} className="stat">
              <span className="stat-label" style={{ color: r.color }}>{r.label}</span>
              <span className="stat-value">{r.count}</span>
              <span className="stat-sub">SKU-er med pris</span>
            </div>
          ))}
        </div>
      )}

      {/* Snittpris-graf: alle produkter sammenlignet */}
      {!loading && avgChartData.rows.length > 0 && (
        <div className="charts-grid">
          <div className="chart-card chart-card-wide">
            <h3 className="chart-title">Gjennomsnittspris per produkt</h3>
            <p className="chart-desc">
              Snittpris på tvers av kjedene for {scopeLabel}
              {avgChartData.total > avgChartData.rows.length
                ? ` — viser de ${avgChartData.rows.length} dyreste av ${avgChartData.total}`
                : ` (${avgChartData.rows.length} produkter)`}.
              Fargen viser hvilken kjede som er billigst.
            </p>
            <ResponsiveContainer width="100%" height={Math.max(260, avgChartData.rows.length * 26)}>
              <BarChart data={avgChartData.rows} layout="vertical" margin={{ top: 5, right: 24, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fontSize: 11, fontFamily: 'inherit' }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={v => `${v} kr`}
                />
                <YAxis
                  dataKey="name"
                  type="category"
                  width={190}
                  tick={{ fontSize: 10, fontFamily: 'inherit' }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip content={<ProductAvgTooltip />} cursor={{ fill: 'var(--bg)' }} />
                <Bar {...CHART_ANIM} dataKey="avg" name="Snittpris" radius={[0, 4, 4, 0]}>
                  {avgChartData.rows.map((e, i) => <Cell key={i} fill={e.color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className="table-wrap">
        {loading ? (
          <TableSkeleton cols={7} label="Henter priser..." />
        ) : error ? (
          <div className="empty">
            <div className="empty-icon">&#9888;</div>
            <div className="empty-text">{error}</div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="empty">
            <div className="empty-icon">&#9678;</div>
            <div className="empty-text">
              {data.length === 0 ? 'Ingen produkter i datagrunnlaget' : 'Ingen SKU-er matcher søket'}
            </div>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th onClick={() => handleSort('varenummer')} className={sortCol === 'varenummer' ? 'sorted' : ''} style={{ width: '110px' }}>
                  Varenummer {renderSortIcon('varenummer')}
                </th>
                <th onClick={() => handleSort('produkt')} className={sortCol === 'produkt' ? 'sorted' : ''}>
                  Produkt {renderSortIcon('produkt')}
                </th>
                {retailers.map(r => (
                  <th key={r.key} onClick={() => handleSort(r.key)} className={`th-price ${sortCol === r.key ? 'sorted' : ''}`} style={{ textAlign: 'right' }}>
                    <div className="retailer-header" style={{ justifyContent: 'flex-end' }}>
                      <span className="retailer-dot" style={{ background: r.color }}></span>
                      <span className="retailer-label">{r.label}</span> {renderSortIcon(r.key)}
                    </div>
                  </th>
                ))}
                <th onClick={() => handleSort('laveste')} className={sortCol === 'laveste' ? 'sorted' : ''} style={{ textAlign: 'right' }}>
                  Lavest {renderSortIcon('laveste')}
                </th>
                <th onClick={() => handleSort('snitt')} className={sortCol === 'snitt' ? 'sorted' : ''} style={{ textAlign: 'right' }}>
                  Snitt {renderSortIcon('snitt')}
                </th>
                <th onClick={() => handleSort('spread')} className={sortCol === 'spread' ? 'sorted' : ''} style={{ textAlign: 'right' }}>
                  Spread {renderSortIcon('spread')}
                </th>
                <th style={{ textAlign: 'right', width: '130px' }}>Billigst kjede</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(row => {
                const c = row._calc
                return (
                  <tr key={row.id}>
                    <td>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                        {row.varenummer || '—'}
                      </span>
                    </td>
                    <td className="td-product">
                      <div className="product-name">{row.produkt}</div>
                      <div className="product-brand">{row.merke}</div>
                    </td>
                    {retailers.map(r => {
                      const val = row[r.key]
                      const isMin = val != null && val === c.min && c.max !== c.min
                      const isMax = val != null && val === c.max && c.max !== c.min
                      return (
                        <td key={r.key} className="td-price" data-label={r.label}>
                          {val == null ? (
                            <span className="price-null">—</span>
                          ) : (
                            <span className={`price-val ${isMin ? 'price-lowest' : isMax ? 'price-highest' : ''}`}>
                              {fmt(val)}
                              {isMin && <span className="price-dot" style={{ background: '#1D6A3A' }}></span>}
                            </span>
                          )}
                        </td>
                      )
                    })}
                    <td className="td-price" data-label="Lavest">
                      {c.min != null ? (
                        <span className="price-val price-lowest">{fmt(c.min)}</span>
                      ) : <span className="price-null">—</span>}
                    </td>
                    <td className="td-price" data-label="Snitt">
                      {c.avg != null ? (
                        <span className="price-val">{fmt(c.avg)}</span>
                      ) : <span className="price-null">—</span>}
                    </td>
                    <td className="td-diff" data-label="Spread">
                      {c.spread != null && c.spread > 0 ? (
                        <span className="diff-val diff-pos">
                          +{fmt(c.spread)}{c.spreadPct != null ? ` (${c.spreadPct.toFixed(0)}%)` : ''}
                        </span>
                      ) : c.spread === 0 ? (
                        <span className="diff-val diff-zero">—</span>
                      ) : (
                        <span className="price-null">—</span>
                      )}
                    </td>
                    <td className="td-price" data-label="Billigst kjede" style={{ textAlign: 'right' }}>
                      {c.cheapest ? (
                        <span className="retailer-header" style={{ justifyContent: 'flex-end' }}>
                          <span className="retailer-dot" style={{ background: c.cheapest.color }}></span>
                          <span className="retailer-label">{c.cheapest.label}</span>
                        </span>
                      ) : <span className="price-null">—</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      <Footer left={'Karo Healthcare Norway · Priskart solpleie'} />
    </div>
  )
}
