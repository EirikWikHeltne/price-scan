// Nøkkeltall for Grafer-siden, regnet ut fra radene i /api/priser (én rad
// per produkt med én kolonne per kjede).
//
// Prisindeks: et produkts pris hos en kjede delt på snittet av prisene
// produktet har hos alle kjedene, ganger 100. 100 er markedssnittet, 95 er
// fem prosent under. Bare produkter med pris hos minst to kjeder er med.
// I motsetning til et rent prissnitt per kjede sammenligner indeksen like
// varer, så en kjede ser ikke billig ut bare fordi den fører billigere varer.

import { ALL } from './categories.js'

// Færre produkter enn dette bak et tall, og det vises ikke.
export const MIN_ANTALL = 3

export const SEGMENTS = ['Karo', 'Egne merker', 'Andre']

function priceOf(row, key) {
  const v = row?.[key]
  if (v === null || v === undefined || v === '') return null
  const n = Number(v)
  // 0 kr betyr at kjeden ikke fører produktet, ikke at det er gratis.
  return Number.isFinite(n) && n > 0 ? n : null
}

const mean = xs => xs.reduce((s, v) => s + v, 0) / xs.length

export function median(xs) {
  if (!xs.length) return null
  const s = [...xs].sort((a, b) => a - b)
  const mid = s.length >> 1
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2
}

// Prisene et produkt har, og indeksen per kjede. `index` er null når
// produktet har pris hos færre enn to kjeder.
export function productPrices(row, keys) {
  const found = []
  for (const key of keys) {
    const p = priceOf(row, key)
    if (p !== null) found.push([key, p])
  }
  if (!found.length) return null
  const values = found.map(f => f[1])
  const snitt = mean(values)
  const result = { snitt, min: Math.min(...values), max: Math.max(...values), index: null }
  if (found.length >= 2) {
    result.index = {}
    for (const [key, p] of found) result.index[key] = (p / snitt) * 100
  }
  return result
}

// Nivået rett under det som er valgt i kategorifilteret: det er disse
// gruppene det gir mening å sammenligne.
export function groupKeyFor(filter) {
  if (!filter || filter.kategori === ALL) return 'kategori'
  if (filter.niva1 === ALL) return 'niva1'
  if (filter.niva2 === ALL) return 'niva2'
  return 'niva3'
}

// Snittindeks per kjede: [{ key, index, antall }], lavest indeks først.
// Kjeder uten sammenlignbare produkter er utelatt.
export function retailerIndex(rows, keys) {
  const sums = Object.fromEntries(keys.map(k => [k, { sum: 0, antall: 0 }]))
  for (const row of rows) {
    const index = productPrices(row, keys)?.index
    if (!index) continue
    for (const key in index) {
      sums[key].sum += index[key]
      sums[key].antall++
    }
  }
  return keys
    .filter(k => sums[k].antall > 0)
    .map(k => ({ key: k, index: sums[k].sum / sums[k].antall, antall: sums[k].antall }))
    .sort((a, b) => a.index - b.index)
}

// Snittindeks per gruppe og kjede:
//   [{ gruppe, antall, celler: { <kjede>: { index, antall } } }]
// Flest sammenlignbare produkter først. Produkter uten verdi på `groupKey`
// er utelatt.
export function indexMatrix(rows, keys, groupKey) {
  const groups = new Map()
  for (const row of rows) {
    const gruppe = row?.[groupKey]
    if (!gruppe) continue
    const index = productPrices(row, keys)?.index
    if (!index) continue
    let g = groups.get(gruppe)
    if (!g) groups.set(gruppe, g = { gruppe, antall: 0, celler: {} })
    g.antall++
    for (const key in index) {
      const c = g.celler[key] || (g.celler[key] = { sum: 0, antall: 0 })
      c.sum += index[key]
      c.antall++
    }
  }
  return [...groups.values()]
    .map(g => ({
      gruppe: g.gruppe,
      antall: g.antall,
      celler: Object.fromEntries(
        Object.entries(g.celler).map(([k, c]) => [k, { index: c.sum / c.antall, antall: c.antall }])
      ),
    }))
    .sort((a, b) => b.antall - a.antall || a.gruppe.localeCompare(b.gruppe, 'nb'))
}

// Prisnivået til hvert segment innen hver gruppe:
//   [{ gruppe, antall, median, segmenter: { Karo: { median, antall, avvik } } }]
// Et produkts pris er snittet av prisene det har hos kjedene; segmentets
// pris er medianen av produktene. `avvik` er prosent over eller under
// medianen for alle produktene i gruppen. Et segment trenger MIN_ANTALL
// produkter for å telle, og en gruppe trenger to slike segmenter.
export function segmentLadder(rows, keys, groupKey) {
  const groups = new Map()
  for (const row of rows) {
    const gruppe = row?.[groupKey]
    if (!gruppe || !SEGMENTS.includes(row.segment)) continue
    const prices = productPrices(row, keys)
    if (!prices) continue
    let g = groups.get(gruppe)
    if (!g) groups.set(gruppe, g = { alle: [], segmenter: {} })
    g.alle.push(prices.snitt)
    ;(g.segmenter[row.segment] || (g.segmenter[row.segment] = [])).push(prices.snitt)
  }
  const result = []
  for (const [gruppe, g] of groups) {
    const total = median(g.alle)
    const segmenter = {}
    for (const s of SEGMENTS) {
      const values = g.segmenter[s]
      if (!values || values.length < MIN_ANTALL) continue
      const m = median(values)
      segmenter[s] = { median: m, antall: values.length, avvik: (m / total - 1) * 100 }
    }
    if (Object.keys(segmenter).length < 2) continue
    result.push({ gruppe, antall: g.alle.length, median: total, segmenter })
  }
  return result.sort((a, b) => b.antall - a.antall || a.gruppe.localeCompare(b.gruppe, 'nb'))
}

// Medianen av (dyrest − billigst) / billigst i prosent, og hvor mange
// produkter som har pris hos minst to kjeder.
export function spreadSummary(rows, keys) {
  const spreads = []
  for (const row of rows) {
    const p = productPrices(row, keys)
    if (p?.index) spreads.push((p.max / p.min - 1) * 100)
  }
  return { antall: spreads.length, medianPct: median(spreads) }
}
