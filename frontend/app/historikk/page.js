'use client'
import { useState, useEffect, useMemo, useCallback, useDeferredValue, useRef } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts'
import { CHART_ANIM, PRICE_DOMAIN } from '@/lib/chartTheme'
import Header from '@/components/Header'
import Footer from '@/components/Footer'
import { fetchJson } from '@/lib/fetchJson'
import { deriveRetailers } from '@/lib/retailers'
import CategoryFilter from '@/components/CategoryFilter'
import { NO_FILTER, matchesLevels } from '@/lib/categories'
import { fmt, fmtDate, fmtDateShort } from '@/lib/format'
import { useLastUpdated } from '@/lib/useLastUpdated'
import { matchesSearch } from '@/lib/search'

const TIME_RANGES = [
  { label: '7 dager', value: 7 },
  { label: '30 dager', value: 30 },
  { label: '90 dager', value: 90 },
  { label: 'Alt', value: 0 },
]

function HistoryTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">
        {fmtDate(label)}
      </div>
      {payload.map(p => (
        <div key={p.name} className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ background: p.color }}></span>
          {p.name}: {fmt(p.value)} kr
        </div>
      ))}
    </div>
  )
}

// Produktlisten i sidefeltet tegnes ikke lenger enn dette; resten nås med
// søk eller kategorivalg.
const MAX_LISTED = 200

export default function HistorikkPage() {
  const [products, setProducts] = useState([])
  const [historyData, setHistoryData] = useState([])
  const [loading, setLoading] = useState(true)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [selectedProduct, setSelectedProduct] = useState(null)
  const [dager, setDager] = useState(30)
  const [cat, setCat] = useState(NO_FILTER)
  const [search, setSearch] = useState('')
  const deferredSearch = useDeferredValue(search)
  const [tableNotFound, setTableNotFound] = useState(false)
  const [historyError, setHistoryError] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const lastUpdated = useLastUpdated(products)

  // Produktliste med nåværende priser (deles med Tabell-siden via cache)
  useEffect(() => {
    fetchJson('/api/priser')
      .catch(() => [])
      .then(productData => {
        setProducts(Array.isArray(productData) ? productData : [])
        setLoading(false)
      })
  }, [])

  // Fetch history when product is selected
  // Teller opp for hvert kall, slik at et tregt svar for et tidligere valgt
  // produkt ikke overskriver grafen for det som er valgt nå.
  const requestId = useRef(0)

  const fetchHistory = useCallback(async (product) => {
    if (!product) return
    const id = ++requestId.current
    const isStale = () => id !== requestId.current
    setHistoryLoading(true)
    setTableNotFound(false)
    setHistoryError(null)
    try {
      const params = new URLSearchParams()
      if (product.varenummer) params.set('varenummer', product.varenummer)
      else params.set('produkt', product.produkt)
      params.set('dager', dager.toString())

      const json = await fetchJson(`/api/historikk?${params}`)
      if (isStale()) return

      if (json.code === 'TABLE_NOT_FOUND') {
        setTableNotFound(true)
        setHistoryData([])
      } else if (Array.isArray(json)) {
        setHistoryData(json)
      } else {
        setHistoryError(json.error || 'Kunne ikke hente prishistorikk')
        setHistoryData([])
      }
    } catch {
      if (isStale()) return
      setHistoryError('Kunne ikke hente prishistorikk. Prøv igjen.')
      setHistoryData([])
    }
    setHistoryLoading(false)
  }, [dager])

  useEffect(() => {
    if (selectedProduct) fetchHistory(selectedProduct)
  }, [selectedProduct, fetchHistory])

  const retailers = useMemo(() => {
    const all = [...products, ...historyData]
    return deriveRetailers(all)
  }, [products, historyData])

  const filteredProducts = useMemo(() => {
    let d = products
    d = d.filter(r => matchesLevels(r, cat))
    if (deferredSearch.trim()) d = d.filter(r => matchesSearch(r, deferredSearch))
    return d
  }, [products, cat, deferredSearch])

  // Format history data for the chart
  const chartData = useMemo(() => {
    if (!historyData.length) return []
    const byDate = {}
    historyData.forEach(row => {
      const date = row.dato?.slice(0, 10) || row.sist_oppdatert?.slice(0, 10)
      if (!date) return
      if (!byDate[date]) byDate[date] = { dato: date }
      retailers.forEach(r => {
        if (row[r.key] != null) byDate[date][r.key] = Number(row[r.key])
      })
    })
    return Object.values(byDate).sort((a, b) => a.dato.localeCompare(b.dato))
  }, [historyData, retailers])

  function handleProductSelect(p) {
    setSelectedProduct(p)
    // On mobile, collapse sidebar after selection
    if (typeof window !== 'undefined' && window.innerWidth <= 768) {
      setSidebarOpen(false)
    }
  }

  return (
    <div className="app">
      <Header active="/historikk" lastUpdated={lastUpdated} />

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
        <CategoryFilter rows={products} value={cat} onChange={setCat} />
      </div>

      <div className="historikk-layout">
        {/* Product list sidebar */}
        <div className={`historikk-sidebar ${!sidebarOpen ? 'collapsed' : ''}`}>
          <button className="historikk-sidebar-header" onClick={() => setSidebarOpen(!sidebarOpen)} style={{ cursor: 'pointer', background: 'none', border: 'none', width: '100%', textAlign: 'left', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-faint)' }}>
              Velg produkt ({filteredProducts.length})
            </span>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-faint)' }}>{sidebarOpen ? '▲' : '▼'}</span>
          </button>
          {sidebarOpen && (
            <>
              {loading ? (
                <div className="loading"><div className="spinner"></div> Laster...</div>
              ) : filteredProducts.length === 0 ? (
                <div className="empty" style={{ padding: '2rem' }}>
                  <div className="empty-text">Ingen produkter funnet</div>
                </div>
              ) : (
                <div className="historikk-product-list">
                  {filteredProducts.slice(0, MAX_LISTED).map(p => (
                    <button
                      key={p.id}
                      className={`historikk-product-item ${selectedProduct?.id === p.id ? 'active' : ''}`}
                      onClick={() => handleProductSelect(p)}
                    >
                      <div className="product-name">{p.produkt}</div>
                      <div className="product-brand">{p.merke}</div>
                      <div className="product-vn">{p.varenummer}</div>
                    </button>
                  ))}
                  {filteredProducts.length > MAX_LISTED && (
                    <div className="cat-path" style={{ padding: '0.75rem' }}>
                      Viser {MAX_LISTED} av {filteredProducts.length}. Søk eller velg kategori for å snevre inn.
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Chart area */}
        <div className="historikk-main">
          {!selectedProduct ? (
            <div className="empty" style={{ padding: '4rem' }}>
              <div className="empty-icon">&#9716;</div>
              <div className="empty-text">Velg et produkt fra listen for å se prishistorikk</div>
            </div>
          ) : (
            <>
              <div className="historikk-chart-header">
                <div>
                  <h2 className="chart-title">{selectedProduct.produkt}</h2>
                  <p className="chart-desc">{selectedProduct.merke} &middot; {selectedProduct.varenummer} &middot; {[selectedProduct.kategori, selectedProduct.niva1, selectedProduct.niva2].filter(Boolean).join(' › ')}</p>
                </div>
                <div className="filter-tabs">
                  {TIME_RANGES.map(r => (
                    <button
                      key={r.value}
                      className={`tab ${dager === r.value ? 'active' : ''}`}
                      onClick={() => setDager(r.value)}
                    >
                      {r.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Current prices card */}
              <div className="historikk-current-prices">
                <div className="historikk-prices-label">Nåværende priser</div>
                <div className="historikk-prices-grid">
                  {retailers.map(r => (
                    <div key={r.key} className="historikk-price-card">
                      <span className="retailer-dot" style={{ background: r.color }}></span>
                      <span className="historikk-price-retailer">{r.label}</span>
                      <span className="historikk-price-value">
                        {selectedProduct[r.key] != null
                          ? `${fmt(selectedProduct[r.key])} kr`
                          : '—'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {historyError ? (
                <div className="chart-card" style={{ marginTop: '1rem' }}>
                  <div className="empty" style={{ padding: '3rem' }}>
                    <div className="empty-icon">&#9888;</div>
                    <div className="empty-text">{historyError}</div>
                    <button
                      className="tab active"
                      style={{ marginTop: '1rem' }}
                      onClick={() => fetchHistory(selectedProduct)}
                    >
                      Prøv igjen
                    </button>
                  </div>
                </div>
              ) : tableNotFound ? (
                <div className="chart-card" style={{ marginTop: '1rem' }}>
                  <div className="empty" style={{ padding: '3rem' }}>
                    <div className="empty-icon">&#128202;</div>
                    <div className="empty-text">Prishistorikk er ikke tilgjengelig ennå</div>
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '0.5rem' }}>
                      Historiske prisdata vil vises her når data er tilgjengelig.
                    </p>
                  </div>
                </div>
              ) : historyLoading ? (
                <div className="chart-card" style={{ marginTop: '1rem' }} role="status" aria-label="Henter prishistorikk">
                  <span className="skeleton skeleton-title" />
                  <span className="skeleton skeleton-line skeleton-line-short" />
                  <span className="skeleton skeleton-chart" style={{ height: 350 }} />
                </div>
              ) : chartData.length === 0 ? (
                <div className="chart-card" style={{ marginTop: '1rem' }}>
                  <div className="empty" style={{ padding: '3rem' }}>
                    <div className="empty-icon">&#128202;</div>
                    <div className="empty-text">Ingen historiske data for dette produktet</div>
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '0.5rem' }}>
                      Det finnes ingen prishistorikk for den valgte perioden.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="chart-card" style={{ marginTop: '1rem' }}>
                  <h3 className="chart-title">Prisutvikling</h3>
                  <p className="chart-desc">{chartData.length} datapunkter i perioden</p>
                  <ResponsiveContainer width="100%" height={350}>
                    <LineChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                      <XAxis
                        dataKey="dato"
                        tick={{ fontSize: 10, fontFamily: 'inherit' }}
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={fmtDateShort}
                      />
                      <YAxis
                        tick={{ fontSize: 11, fontFamily: 'inherit' }}
                        axisLine={false}
                        tickLine={false}
                        width={55}
                        domain={PRICE_DOMAIN}
                        tickFormatter={v => `${Math.round(v)} kr`}
                      />
                      <Tooltip content={<HistoryTooltip />} />
                      <Legend
                        wrapperStyle={{ fontSize: '0.75rem', fontFamily: 'inherit' }}
                      />
                      {retailers.map(r => (
                        <Line
                          {...CHART_ANIM}
                          key={r.key}
                          type="monotone"
                          dataKey={r.key}
                          name={r.label}
                          stroke={r.color}
                          strokeWidth={2}
                          dot={chartData.length <= 31 ? { r: 3, strokeWidth: 2, fill: 'var(--surface)' } : false}
                          activeDot={{ r: 5 }}
                          connectNulls
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                  {chartData.length === 1 && (
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '0.75rem', textAlign: 'center' }}>
                      Kun nåværende priser tilgjengelig — historiske data vil bygges opp over tid.
                    </p>
                  )}
                </div>
              )}

              {/* History table */}
              {chartData.length > 0 && (
                <div className="chart-card" style={{ marginTop: '1rem' }}>
                  <h3 className="chart-title">Prisdata</h3>
                  <div className="table-wrap" style={{ padding: 0 }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Dato</th>
                          {retailers.map(r => (
                            <th key={r.key} style={{ textAlign: 'right' }}>
                              <div className="retailer-header" style={{ justifyContent: 'flex-end' }}>
                                <span className="retailer-dot" style={{ background: r.color }}></span>
                                <span className="retailer-label">{r.label}</span>
                              </div>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {[...chartData].reverse().map(row => (
                          <tr key={row.dato}>
                            <td>{fmtDate(row.dato)}</td>
                            {retailers.map(r => (
                              <td key={r.key} className="td-price">
                                {row[r.key] != null
                                  ? <span className="price-val">{fmt(row[r.key])}</span>
                                  : <span className="price-null">—</span>}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <Footer />
    </div>
  )
}
