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
import CategoryFilter from '@/components/CategoryFilter'
import { NO_FILTER, matchesLevels } from '@/lib/categories'
import { fmt } from '@/lib/format'
import InsightCharts from '@/components/InsightCharts'
import { SEGMENTS, groupKeyFor, retailerIndex, spreadSummary } from '@/lib/insights'

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
  const [cat, setCat]         = useState(NO_FILTER)
  const [merke, setMerke]     = useState('alle')
  const [segment, setSegment] = useState('alle')

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

  const brands = useMemo(() => {
    const filtered = data.filter(r => matchesLevels(r, cat))
    return [...new Set(filtered.map(r => r.merke).filter(Boolean))].sort()
  }, [data, cat])

  const filtered = useMemo(() => {
    let d = data.filter(r => matchesLevels(r, cat))
    if (merke !== 'alle') d = d.filter(r => r.merke === merke)
    if (segment !== 'alle') d = d.filter(r => r.segment === segment)
    return d
  }, [data, cat, merke, segment])

  // Segmentene finnes først når kategoritreet er lagt inn i databasen.
  const segments = useMemo(
    () => SEGMENTS.filter(s => data.some(r => r.segment === s)),
    [data]
  )
  const groupKey = groupKeyFor(cat)

  // Nøkkeltall over grafene
  const summary = useMemo(() => {
    const keys = retailers.map(r => r.key)
    const labels = Object.fromEntries(retailers.map(r => [r.key, r.label]))
    const index = retailerIndex(filtered, keys).map(d => ({ ...d, label: labels[d.key] }))
    return {
      ...spreadSummary(filtered, keys),
      lowest: index.length > 1 ? index[0] : null,
      highest: index.length > 1 ? index[index.length - 1] : null,
    }
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
        <CategoryFilter rows={data} value={cat} onChange={next => { setCat(next); setMerke('alle') }} />
        <select
          className="brand-select"
          aria-label="Merke"
          value={merke}
          onChange={e => setMerke(e.target.value)}
        >
          <option value="alle">Alle merker</option>
          {brands.map(b => <option key={b} value={b}>{b}</option>)}
        </select>
        {segments.length > 1 && (
          <select
            className="brand-select"
            aria-label="Segment"
            value={segment}
            onChange={e => setSegment(e.target.value)}
          >
            <option value="alle">Alle segmenter</option>
            {segments.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
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
        <>
        <div className="stats-bar">
          <div className="stat">
            <span className="stat-label">Sammenlignbare produkter</span>
            <span className="stat-value">{summary.antall}</span>
            <span className="stat-sub">med pris hos minst to kjeder</span>
          </div>
          {summary.lowest && (
            <div className="stat">
              <span className="stat-label">Lavest prisnivå</span>
              <span className="stat-value">{summary.lowest.label}</span>
              <span className="stat-sub">indeks {fmt(summary.lowest.index)}</span>
            </div>
          )}
          {summary.highest && (
            <div className="stat">
              <span className="stat-label">Høyest prisnivå</span>
              <span className="stat-value">{summary.highest.label}</span>
              <span className="stat-sub">indeks {fmt(summary.highest.index)}</span>
            </div>
          )}
          {summary.medianPct != null && (
            <div className="stat">
              <span className="stat-label">Typisk prisforskjell</span>
              <span className="stat-value">{fmt(summary.medianPct)} %</span>
              <span className="stat-sub">median, dyrest mot billigst</span>
            </div>
          )}
        </div>
        <div className="charts-grid">
          <InsightCharts
            rows={filtered}
            retailers={retailers}
            groupKey={groupKey}
            hasSegments={segments.length > 1 && segment === 'alle'}
          />

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
        </>
      )}

      <Footer left="Karo Healthcare Norway" />
    </div>
  )
}
