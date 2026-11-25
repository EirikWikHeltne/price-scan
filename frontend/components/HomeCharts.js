'use client'
import { useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, PieChart, Pie, RadarChart, Radar,
  PolarGrid, PolarAngleAxis, PolarRadiusAxis, AreaChart, Area,
} from 'recharts'
import { CHART_ANIM } from '@/lib/chartTheme'
import { fmt, fmtShort } from '@/lib/format'

// Grafene på Tabell-siden. Ligger i egen komponent slik at recharts kan
// lastes etter tabellen (via next/dynamic) og ikke forsinker første visning.

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{label}</div>
      {payload.map(p => (
        <div key={p.name || p.dataKey} className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ background: p.payload?.color || p.color || p.fill }}></span>
          {p.name}: {fmt(p.value)} kr
        </div>
      ))}
    </div>
  )
}

function PieTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-row">
        <span className="chart-tooltip-dot" style={{ background: payload[0].payload?.color }}></span>
        {payload[0].name}: {payload[0].value} produkter
      </div>
    </div>
  )
}

function renderPieLabel({ name, value, cx, x, y }) {
  const anchor = x > cx ? 'start' : 'end'
  return (
    <text x={x} y={y} textAnchor={anchor} dominantBaseline="central" fontSize={11} fontFamily="inherit" fill="var(--text)">
      {name} ({value})
    </text>
  )
}

export default function HomeCharts({ visible, retailers }) {
  // Average price per retailer
  const avgByRetailer = useMemo(() => {
    if (!visible.length) return []
    return retailers.map(r => {
      const vals = visible.map(row => row[r.key]).filter(v => v != null).map(Number)
      return {
        name: r.label,
        snitt: vals.length ? +(vals.reduce((s, v) => s + v, 0) / vals.length).toFixed(2) : 0,
        color: r.color,
      }
    })
  }, [visible, retailers])

  // Cheapest retailer distribution
  const cheapestDist = useMemo(() => {
    if (!visible.length) return []
    const counts = {}
    retailers.forEach(r => { counts[r.label] = 0 })
    visible.forEach(row => {
      let min = Infinity, winner = null
      retailers.forEach(r => {
        if (row[r.key] != null && Number(row[r.key]) < min) {
          min = Number(row[r.key]); winner = r.label
        }
      })
      if (winner) counts[winner]++
    })
    return retailers.map(r => ({ name: r.label, value: counts[r.label], color: r.color })).filter(e => e.value > 0)
  }, [visible, retailers])

  // Price range distribution (histogram-like)
  const priceDistribution = useMemo(() => {
    if (!visible.length) return []
    const prices = visible.map(r => r.laveste_pris).filter(v => v != null).map(Number)
    if (!prices.length) return []
    const min = Math.floor(Math.min(...prices))
    const max = Math.ceil(Math.max(...prices))
    const step = Math.max(1, Math.ceil((max - min) / 8))
    const buckets = []
    for (let i = min; i < max; i += step) {
      const lo = i
      const hi = i + step
      const count = prices.filter(p => p >= lo && p < hi).length
      buckets.push({ range: `${fmtShort(lo)}-${fmtShort(hi)}`, count, lo, hi })
    }
    return buckets
  }, [visible])

  // Category comparison radar
  const categoryRadar = useMemo(() => {
    if (!visible.length) return []
    const cats = [...new Set(visible.map(r => r.kategori).filter(Boolean))]
    return cats.map(cat => {
      const catRows = visible.filter(r => r.kategori === cat)
      const result = { kategori: cat }
      retailers.forEach(r => {
        const vals = catRows.map(row => row[r.key]).filter(v => v != null).map(Number)
        result[r.key] = vals.length ? +(vals.reduce((s, v) => s + v, 0) / vals.length).toFixed(2) : 0
      })
      return result
    })
  }, [visible, retailers])

  // Spread distribution by category
  const spreadByCategory = useMemo(() => {
    if (!visible.length) return []
    const cats = [...new Set(visible.map(r => r.kategori).filter(Boolean))]
    return cats.map(cat => {
      const catRows = visible.filter(r => r.kategori === cat)
      const spreads = catRows.map(row => {
        const prices = retailers.map(r => row[r.key]).filter(v => v != null).map(Number)
        if (prices.length < 2) return 0
        return Math.max(...prices) - Math.min(...prices)
      }).filter(s => s > 0)
      const avgSpread = spreads.length ? +(spreads.reduce((s, v) => s + v, 0) / spreads.length).toFixed(2) : 0
      const maxSpread = spreads.length ? +Math.max(...spreads).toFixed(2) : 0
      return { name: cat, snittSpread: avgSpread, maxSpread }
    }).sort((a, b) => b.snittSpread - a.snittSpread)
  }, [visible, retailers])

  return (
    <div className="charts-grid table-charts">
      {/* Average price per retailer */}
      <div className="chart-card">
        <h3 className="chart-title">Snittpris per apotek</h3>
        <p className="chart-desc">Gjennomsnittlig pris basert på {visible.length} produkter</p>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={avgByRetailer} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 11, fontFamily: 'inherit' }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fontFamily: 'inherit' }} axisLine={false} tickLine={false} width={50} />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'var(--bg)' }} />
            <Bar {...CHART_ANIM} dataKey="snitt" name="Snittpris" radius={[4, 4, 0, 0]}>
              {avgByRetailer.map(e => <Cell key={e.name} fill={e.color} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Cheapest retailer pie */}
      <div className="chart-card">
        <h3 className="chart-title">Billigst oftest</h3>
        <p className="chart-desc">Hvilken kjede har lavest pris flest ganger</p>
        <ResponsiveContainer width="100%" height={260}>
          <PieChart margin={{ top: 10, right: 80, bottom: 10, left: 80 }}>
            <Pie
              {...CHART_ANIM}
              data={cheapestDist}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              outerRadius={70}
              innerRadius={32}
              label={renderPieLabel}
              labelLine={{ stroke: 'var(--text-faint)' }}
            >
              {cheapestDist.map(e => <Cell key={e.name} fill={e.color} />)}
            </Pie>
            <Tooltip content={<PieTooltip />} />
          </PieChart>
        </ResponsiveContainer>
      </div>

      {/* Price distribution histogram */}
      {priceDistribution.length > 0 && (
        <div className="chart-card">
          <h3 className="chart-title">Prisfordeling</h3>
          <p className="chart-desc">Fordeling av laveste priser (kr)</p>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={priceDistribution} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="range" tick={{ fontSize: 10, fontFamily: 'inherit' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fontFamily: 'inherit' }} axisLine={false} tickLine={false} width={40} />
              <Tooltip formatter={(v) => [`${v} produkter`, 'Antall']} labelStyle={{ fontFamily: 'inherit' }} />
              <Area {...CHART_ANIM} type="monotone" dataKey="count" name="Antall" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.15} strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Spread by category */}
      {spreadByCategory.length > 1 && (
        <div className="chart-card">
          <h3 className="chart-title">Prisforskjeller per kategori</h3>
          <p className="chart-desc">Gjennomsnittlig og maks spread mellom kjedene</p>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={spreadByCategory} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 10, fontFamily: 'inherit' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fontFamily: 'inherit' }} axisLine={false} tickLine={false} width={40} />
              <Tooltip formatter={(v) => `${fmt(v)} kr`} labelStyle={{ fontFamily: 'inherit' }} />
              <Bar {...CHART_ANIM} dataKey="snittSpread" name="Snitt spread" fill="var(--amber)" radius={[4, 4, 0, 0]} />
              <Bar {...CHART_ANIM} dataKey="maxSpread" name="Maks spread" fill="var(--red)" radius={[4, 4, 0, 0]} opacity={0.5} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Radar chart for category comparison */}
      {categoryRadar.length > 2 && (
        <div className="chart-card chart-card-wide">
          <h3 className="chart-title">Kategoriprofil per apotek</h3>
          <p className="chart-desc">Gjennomsnittspriser per kategori og kjede</p>
          <ResponsiveContainer width="100%" height={320}>
            <RadarChart data={categoryRadar} cx="50%" cy="50%" outerRadius="70%">
              <PolarGrid stroke="var(--border)" />
              <PolarAngleAxis dataKey="kategori" tick={{ fontSize: 11, fontFamily: 'inherit', fill: 'var(--text)' }} />
              <PolarRadiusAxis tick={{ fontSize: 10, fontFamily: 'inherit' }} />
              {retailers.map(r => (
                <Radar {...CHART_ANIM} key={r.key} name={r.label} dataKey={r.key} stroke={r.color} fill={r.color} fillOpacity={0.1} strokeWidth={2} />
              ))}
              <Tooltip formatter={(v) => `${fmt(v)} kr`} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
