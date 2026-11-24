'use client'
import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, Cell, PieChart, Pie, AreaChart, Area,
  ScatterChart, Scatter, ZAxis,
} from 'recharts'
import { CHART_ANIM } from '@/lib/chartTheme'
import Header from '@/components/Header'
import Footer from '@/components/Footer'
import { ChartSkeleton } from '@/components/Skeleton'
import { fetchJson } from '@/lib/fetchJson'
import { deriveRetailers } from '@/lib/retailers'
import { fmt } from '@/lib/format'

function GrafTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{label}</div>
      {payload.map(p => (
        <div key={p.name} className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ background: p.payload?.color || p.color }}></span>
          {fmt(p.value)} kr
        </div>
      ))}
    </div>
  )
}

function renderGrafPieLabel({ name, value, cx, x, y }) {
  const anchor = x > cx ? 'start' : 'end'
  return (
    <text x={x} y={y} textAnchor={anchor} dominantBaseline="central" fontSize={11} fontFamily="inherit" fill="var(--text)">
      {name} ({value})
    </text>
  )
}

export default function GraferPage() {
  const [data, setData]       = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)
  const [kategori, setKategori] = useState('alle')
  const [merke, setMerke]     = useState('alle')

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const json = await fetchJson('/api/priser')
      setData(Array.isArray(json) ? json : [])
    } catch (e) {
      console.error(e)
      setError('Kunne ikke hente priser. Prøv igjen.')
    }
    setLoading(false)
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const retailers = useMemo(() => deriveRetailers(data), [data])

  const categories = useMemo(() => {
    return [...new Set(data.map(r => r.kategori).filter(Boolean))].sort()
  }, [data])

  const brands = useMemo(() => {
    let filtered = data
    if (kategori !== 'alle') filtered = filtered.filter(r => r.kategori === kategori)
    return [...new Set(filtered.map(r => r.merke).filter(Boolean))].sort()
  }, [data, kategori])

  const filtered = useMemo(() => {
    let d = data
    if (kategori !== 'alle') d = d.filter(r => r.kategori === kategori)
    if (merke !== 'alle') d = d.filter(r => r.merke === merke)
    return d
  }, [data, kategori, merke])

  // Chart 1: Average price per retailer
  const avgByRetailer = useMemo(() => {
    return retailers.map(r => {
      const vals = filtered.map(row => row[r.key]).filter(v => v != null).map(Number)
      return {
        name: r.label,
        snitt: vals.length ? +(vals.reduce((s, v) => s + v, 0) / vals.length).toFixed(2) : 0,
        color: r.color,
      }
    })
  }, [filtered, retailers])

  // Chart 2: Cheapest retailer distribution (pie)
  const cheapestDist = useMemo(() => {
    const counts = {}
    retailers.forEach(r => { counts[r.label] = 0 })
    filtered.forEach(row => {
      let min = Infinity, winner = null
      retailers.forEach(r => {
        if (row[r.key] != null && Number(row[r.key]) < min) {
          min = Number(row[r.key]); winner = r.label
        }
      })
      if (winner) counts[winner]++
    })
    return retailers.map(r => ({ name: r.label, value: counts[r.label], color: r.color })).filter(e => e.value > 0)
  }, [filtered, retailers])

  // Chart 3: Top 10 products with biggest spread
  const topSpread = useMemo(() => {
    return filtered
      .map(row => {
        const prices = retailers.map(r => row[r.key]).filter(v => v != null).map(Number)
        if (prices.length < 2) return null
        const min = Math.min(...prices)
        const max = Math.max(...prices)
        const label = row.produkt || ''
        return { name: label.length > 25 ? label.slice(0, 25) + '...' : label, spread: +(max - min).toFixed(2), min, max }
      })
      .filter(Boolean)
      .sort((a, b) => b.spread - a.spread)
      .slice(0, 10)
  }, [filtered, retailers])

  // Chart 4: Price coverage heatmap data
  const coverageData = useMemo(() => {
    const cats = [...new Set(filtered.map(r => r.kategori).filter(Boolean))].sort()
    return cats.map(cat => {
      const catRows = filtered.filter(r => r.kategori === cat)
      const result = { kategori: cat, total: catRows.length }
      retailers.forEach(r => {
        result[r.key] = catRows.filter(row => row[r.key] != null).length
        result[`${r.key}Pct`] = catRows.length ? Math.round(catRows.filter(row => row[r.key] != null).length / catRows.length * 100) : 0
      })
      return result
    })
  }, [filtered, retailers])

  // Chart 5: Min vs Max scatter
  const scatterData = useMemo(() => {
    return filtered
      .map(row => {
        const prices = retailers.map(r => row[r.key]).filter(v => v != null).map(Number)
        if (prices.length < 2) return null
        return {
          min: Math.min(...prices),
          max: Math.max(...prices),
          name: row.produkt,
          spread: +(Math.max(...prices) - Math.min(...prices)).toFixed(2),
        }
      })
      .filter(Boolean)
  }, [filtered, retailers])

  return (
    <div className="app">
      <Header active="/grafer" showLastUpdated={false} />

      <div className="controls">
        <div className="filter-tabs">
          {['alle', ...categories].map(k => (
            <button
              key={k}
              className={`tab ${kategori === k ? 'active' : ''}`}
              onClick={() => { setKategori(k); setMerke('alle') }}
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
          <span className="count-badge">{filtered.length} produkter</span>
        </div>
      </div>

      {loading ? (
        <ChartSkeleton count={4} height={300} />
      ) : error ? (
        <div className="empty">
          <div className="empty-icon">&#9888;</div>
          <div className="empty-text">{error}</div>
          <button className="tab active" style={{ marginTop: '1rem' }} onClick={loadData}>
            Prøv igjen
          </button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty">
          <div className="empty-icon">&#9678;</div>
          <div className="empty-text">Ingen produkter funnet</div>
        </div>
      ) : (
        <div className="charts-grid">
          <div className="chart-card">
            <h3 className="chart-title">Gjennomsnittspris per apotek</h3>
            <p className="chart-desc">Snittpris basert på {filtered.length} produkter</p>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={avgByRetailer} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 11, fontFamily: 'inherit' }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fontFamily: 'inherit' }}
                  axisLine={false}
                  tickLine={false}
                  width={50}
                />
                <Tooltip content={<GrafTooltip />} cursor={{ fill: 'var(--bg)' }} />
                <Bar {...CHART_ANIM} dataKey="snitt" name="Snittpris" radius={[4, 4, 0, 0]}>
                  {avgByRetailer.map(e => (
                    <Cell key={e.name} fill={e.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-card">
            <h3 className="chart-title">Billigst oftest</h3>
            <p className="chart-desc">Hvilken kjede har lavest pris flest ganger</p>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart margin={{ top: 10, right: 80, bottom: 10, left: 80 }}>
                <Pie
                  {...CHART_ANIM}
                  data={cheapestDist}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  innerRadius={40}
                  label={renderGrafPieLabel}
                  labelLine={{ stroke: 'var(--text-faint)' }}
                >
                  {cheapestDist.map(e => (
                    <Cell key={e.name} fill={e.color} />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => `${v} produkter`} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          {/* Coverage per category per retailer */}
          {coverageData.length > 0 && (
            <div className="chart-card">
              <h3 className="chart-title">Prisdekning per kategori</h3>
              <p className="chart-desc">Andel produkter med pris hos hver kjede (%)</p>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={coverageData} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="kategori" tick={{ fontSize: 10, fontFamily: 'inherit' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fontFamily: 'inherit' }} axisLine={false} tickLine={false} width={40} domain={[0, 100]} tickFormatter={v => `${v}%`} />
                  <Tooltip formatter={(v) => `${v}%`} labelStyle={{ fontFamily: 'inherit' }} />
                  <Legend wrapperStyle={{ fontSize: '0.7rem', fontFamily: 'inherit' }} />
                  {retailers.map(r => (
                    <Bar {...CHART_ANIM} key={r.key} dataKey={`${r.key}Pct`} name={r.label} fill={r.color} radius={[2, 2, 0, 0]} opacity={0.8} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Min vs Max scatter */}
          {scatterData.length > 0 && (
            <div className="chart-card">
              <h3 className="chart-title">Laveste vs. høyeste pris</h3>
              <p className="chart-desc">Hvert punkt er et produkt — avstand fra linjen viser prisforskjell</p>
              <ResponsiveContainer width="100%" height={300}>
                <ScatterChart margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis type="number" dataKey="min" name="Laveste" tick={{ fontSize: 10, fontFamily: 'inherit' }} axisLine={false} tickLine={false} tickFormatter={v => `${v} kr`} />
                  <YAxis type="number" dataKey="max" name="Høyeste" tick={{ fontSize: 10, fontFamily: 'inherit' }} axisLine={false} tickLine={false} width={55} tickFormatter={v => `${v} kr`} />
                  <ZAxis type="number" dataKey="spread" range={[30, 200]} name="Spread" />
                  <Tooltip
                    formatter={(v, name) => [`${fmt(v)} kr`, name]}
                    labelFormatter={(_, payload) => payload?.[0]?.payload?.name || ''}
                    contentStyle={{ fontFamily: 'inherit', fontSize: '0.75rem' }}
                  />
                  <Scatter {...CHART_ANIM} data={scatterData} fill="var(--accent)" fillOpacity={0.4} stroke="var(--accent)" strokeWidth={1} />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className="chart-card chart-card-wide">
            <h3 className="chart-title">Topp 10 største prisforskjeller</h3>
            <p className="chart-desc">Produkter med størst differanse mellom billigst og dyrest</p>
            {topSpread.length === 0 ? (
              <div className="empty" style={{ padding: '2rem' }}>
                <div className="empty-text">For få priser å sammenligne</div>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={Math.max(260, topSpread.length * 36)}>
                <BarChart data={topSpread} layout="vertical" margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                  <XAxis
                    type="number"
                    tick={{ fontSize: 11, fontFamily: 'inherit' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    dataKey="name"
                    type="category"
                    width={140}
                    tick={{ fontSize: 10, fontFamily: 'inherit' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip formatter={(v) => `${fmt(v)} kr`} labelStyle={{ fontFamily: 'inherit' }} />
                  <Bar {...CHART_ANIM} dataKey="spread" name="Prisforskjell" fill="var(--red)" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      )}

      <Footer left="Karo Healthcare Norway" />
    </div>
  )
}
