'use client'
import { useMemo, useState, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { fmt } from '@/lib/format'
import {
  MIN_ANTALL, SEGMENTS, retailerIndex, indexMatrix, segmentLadder,
} from '@/lib/insights'

// Tre grafer som sammenligner like varer: prisindeks per kjede, indeks per
// gruppe og kjede, og prisnivået til Karo mot egne merker og andre.
// De tegnes med vanlig HTML/CSS (se «INNSIKT» i globals.css).

const HEAT_ROWS = 14
const LADDER_ROWS = 12

const pct1 = new Intl.NumberFormat('nb-NO', { maximumFractionDigits: 1, minimumFractionDigits: 1, signDisplay: 'exceptZero' })
const pct0 = new Intl.NumberFormat('nb-NO', { maximumFractionDigits: 0, signDisplay: 'exceptZero' })
const idx0 = new Intl.NumberFormat('nb-NO', { maximumFractionDigits: 0 })

const GROUP_LABEL = { kategori: 'kategori', niva1: 'nivå 1', niva2: 'nivå 2', niva3: 'nivå 3' }
const SEGMENT_CLASS = { 'Karo': 'seg-karo', 'Egne merker': 'seg-egne', 'Andre': 'seg-andre' }

// Runder opp til et pent aksemaksimum.
function niceMax(value, steps) {
  return steps.find(s => s >= value) ?? steps[steps.length - 1]
}

// Ett verktøytips som følger pekeren, og som også vises ved tastaturfokus.
function useTip() {
  const [tip, setTip] = useState(null)
  const show = useCallback((e, content) => {
    let x = e.clientX, y = e.clientY
    if (!x && !y) { // fokus fra tastatur: plasser ved elementet
      const r = e.currentTarget.getBoundingClientRect()
      x = r.left + r.width / 2
      y = r.top
    }
    setTip({ x, y, content })
  }, [])
  const hide = useCallback(() => setTip(null), [])
  const bind = content => ({
    onMouseMove: e => show(e, content),
    onMouseLeave: hide,
    onFocus: e => show(e, content),
    onBlur: hide,
  })
  // Tegnes rett i <body>: kortene har en transform-animasjon, og inne i dem
  // ville position: fixed blitt regnet fra kortet i stedet for vinduet.
  const node = tip && createPortal(
    <div
      className="chart-tooltip insight-tip"
      role="status"
      style={{
        left: Math.min(tip.x + 14, (typeof window !== 'undefined' ? window.innerWidth : 9999) - 240),
        top: tip.y + 14,
      }}
    >
      {tip.content}
    </div>,
    document.body
  )
  return { bind, node }
}

function DivergingLegend({ low, high }) {
  return (
    <div className="insight-legend" aria-hidden="true">
      <span>{low}</span>
      <span className="insight-legend-ramp"></span>
      <span>{high}</span>
    </div>
  )
}

function IndexBars({ rows, retailers }) {
  const { bind, node } = useTip()
  const data = useMemo(() => {
    const byKey = Object.fromEntries(retailers.map(r => [r.key, r]))
    return retailerIndex(rows, retailers.map(r => r.key)).map(d => ({ ...d, label: byKey[d.key].label, avvik: d.index - 100 }))
  }, [rows, retailers])

  if (data.length < 2) return <div className="insight-empty">For få kjeder med felles produkter</div>

  const max = niceMax(Math.max(...data.map(d => Math.abs(d.avvik))), [2, 5, 10, 15, 20, 30, 50, 100])

  return (
    <>
      <div className="index-bars">
        {data.map(d => {
          const width = Math.min(50, Math.abs(d.avvik) / max * 50)
          const neg = d.avvik < 0
          return (
            <div
              key={d.key}
              className="index-row"
              tabIndex={0}
              {...bind(
                <>
                  <div className="chart-tooltip-label">{d.label}</div>
                  <div>Indeks {fmt(d.index)}</div>
                  <div className="insight-tip-sub">{d.antall} sammenlignbare produkter</div>
                </>
              )}
            >
              <span className="index-name">{d.label}</span>
              <span className="index-track">
                <span
                  className={`index-bar ${neg ? 'neg' : 'pos'}`}
                  style={neg ? { right: '50%', width: `${width}%` } : { left: '50%', width: `${width}%` }}
                ></span>
              </span>
              <span className="index-value">{pct1.format(d.avvik)} %</span>
            </div>
          )
        })}
        <div className="index-row index-axis" aria-hidden="true">
          <span className="index-name"></span>
          <span className="index-track">
            <span style={{ left: 0 }}>−{max} %</span>
            <span style={{ left: '50%' }}>Markedssnitt</span>
            <span style={{ left: '100%' }}>+{max} %</span>
          </span>
          <span className="index-value"></span>
        </div>
      </div>
      {node}
    </>
  )
}

function IndexHeatmap({ rows, retailers, groupKey }) {
  const { bind, node } = useTip()
  const { matrix, cols, total } = useMemo(() => {
    const all = indexMatrix(rows, retailers.map(r => r.key), groupKey)
    const shown = all.slice(0, HEAT_ROWS)
    return {
      matrix: shown,
      total: all.length,
      cols: retailers.filter(r => shown.some(g => g.celler[r.key]?.antall >= MIN_ANTALL)),
    }
  }, [rows, retailers, groupKey])

  if (!matrix.length || cols.length < 2) {
    return <div className="insight-empty">For få sammenlignbare produkter på dette nivået</div>
  }

  // Full farge ved ±15 %: større avvik enn det er sjeldne og skal ikke
  // bleke resten av rutene.
  const shade = index => Math.min(1, Math.abs(index - 100) / 15) * 70

  return (
    <>
      <div className="heat-wrap">
        <table className="heat">
          <thead>
            <tr>
              <th scope="col">{GROUP_LABEL[groupKey].replace(/^./, c => c.toUpperCase())}</th>
              {cols.map(r => <th key={r.key} scope="col">{r.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {matrix.map(g => (
              <tr key={g.gruppe}>
                <th scope="row" title={g.gruppe}>
                  <span className="heat-group">{g.gruppe}</span>
                  <span className="heat-count">{g.antall}</span>
                </th>
                {cols.map(r => {
                  const cell = g.celler[r.key]
                  if (!cell || cell.antall < MIN_ANTALL) {
                    return (
                      <td
                        key={r.key}
                        className="heat-cell heat-none"
                        tabIndex={0}
                        {...bind(
                          <>
                            <div className="chart-tooltip-label">{r.label} · {g.gruppe}</div>
                            <div className="insight-tip-sub">
                              {cell ? `Bare ${cell.antall} sammenlignbare produkter` : 'Ingen sammenlignbare produkter'}
                            </div>
                          </>
                        )}
                      >
                        –
                      </td>
                    )
                  }
                  const neg = cell.index < 100
                  return (
                    <td
                      key={r.key}
                      className="heat-cell"
                      tabIndex={0}
                      style={{ '--heat': `${shade(cell.index)}%`, '--heat-color': neg ? 'var(--div-low)' : 'var(--div-high)' }}
                      {...bind(
                        <>
                          <div className="chart-tooltip-label">{r.label} · {g.gruppe}</div>
                          <div>Indeks {fmt(cell.index)} ({pct1.format(cell.index - 100)} %)</div>
                          <div className="insight-tip-sub">{cell.antall} sammenlignbare produkter</div>
                        </>
                      )}
                    >
                      {idx0.format(cell.index)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="insight-foot">
        <DivergingLegend low="Under markedssnitt" high="Over" />
        {total > matrix.length && (
          <span className="insight-note">Viser de {matrix.length} største av {total} grupper</span>
        )}
      </div>
      {node}
    </>
  )
}

function SegmentLadder({ rows, retailers, groupKey }) {
  const { bind, node } = useTip()
  const { ladder, total } = useMemo(() => {
    const all = segmentLadder(rows, retailers.map(r => r.key), groupKey)
    return { ladder: all.slice(0, LADDER_ROWS), total: all.length }
  }, [rows, retailers, groupKey])

  if (!ladder.length) {
    return <div className="insight-empty">Ingen grupper har nok produkter i minst to segmenter</div>
  }

  const present = SEGMENTS.filter(s => ladder.some(g => g.segmenter[s]))
  const max = niceMax(
    Math.max(...ladder.flatMap(g => Object.values(g.segmenter).map(s => Math.abs(s.avvik)))),
    [10, 20, 30, 50, 75, 100]
  )
  // Avvik utenfor aksen tegnes helt i kanten; tallet står i verktøytipset.
  const pos = avvik => 50 + Math.max(-50, Math.min(50, avvik / max * 50))

  return (
    <>
      <div className="insight-legend insight-legend-series">
        {present.map(s => (
          <span key={s} className="insight-legend-item">
            <span className={`ladder-dot ${SEGMENT_CLASS[s]}`}></span>{s}
          </span>
        ))}
      </div>
      <div className="ladder">
        {ladder.map(g => (
          <div key={g.gruppe} className="ladder-row">
            <span className="ladder-name" title={g.gruppe}>{g.gruppe}</span>
            <span className="ladder-track">
              {present.filter(s => g.segmenter[s]).map(s => {
                const seg = g.segmenter[s]
                return (
                  <span
                    key={s}
                    className={`ladder-dot ${SEGMENT_CLASS[s]}`}
                    style={{ left: `${pos(seg.avvik)}%` }}
                    tabIndex={0}
                    aria-label={`${s}, ${g.gruppe}: ${pct0.format(seg.avvik)} %`}
                    {...bind(
                      <>
                        <div className="chart-tooltip-label">{s} · {g.gruppe}</div>
                        <div>Medianpris {fmt(seg.median)} kr ({pct0.format(seg.avvik)} %)</div>
                        <div className="insight-tip-sub">
                          {seg.antall} produkter · gruppens median {fmt(g.median)} kr
                        </div>
                      </>
                    )}
                  ></span>
                )
              })}
            </span>
            <span className="ladder-value">
              {g.segmenter.Karo ? `${pct0.format(g.segmenter.Karo.avvik)} %` : ''}
            </span>
          </div>
        ))}
        <div className="ladder-row ladder-axis" aria-hidden="true">
          <span className="ladder-name"></span>
          <span className="ladder-track">
            <span style={{ left: 0 }}>−{max} %</span>
            <span style={{ left: '50%' }}>Gruppens median</span>
            <span style={{ left: '100%' }}>+{max} %</span>
          </span>
          <span className="ladder-value">Karo</span>
        </div>
      </div>
      {total > ladder.length && (
        <div className="insight-foot">
          <span className="insight-note">Viser de {ladder.length} største av {total} grupper</span>
        </div>
      )}
      {node}
    </>
  )
}

export default function InsightCharts({ rows, retailers, groupKey, hasSegments }) {
  return (
    <>
      <div className="chart-card">
        <h3 className="chart-title">Prisnivå per kjede</h3>
        <p className="chart-desc">
          Prisindeks for like varer: hvor mye kjeden i snitt ligger over eller under markedssnittet
          på produktene den deler med minst én annen kjede
        </p>
        <IndexBars rows={rows} retailers={retailers} />
      </div>

      <div className="chart-card">
        <h3 className="chart-title">Prisnivå per {GROUP_LABEL[groupKey]} og kjede</h3>
        <p className="chart-desc">
          Prisindeks der 100 er markedssnittet. Tallet etter navnet er antall sammenlignbare produkter
        </p>
        <IndexHeatmap rows={rows} retailers={retailers} groupKey={groupKey} />
      </div>

      {hasSegments && (
        <div className="chart-card chart-card-wide">
          <h3 className="chart-title">Karo mot egne merker og andre</h3>
          <p className="chart-desc">
            Medianpris per segment, som avvik fra medianen for alle produktene i gruppen.
            Tallet til høyre er Karos avvik
          </p>
          <SegmentLadder rows={rows} retailers={retailers} groupKey={groupKey} />
        </div>
      )}
    </>
  )
}
