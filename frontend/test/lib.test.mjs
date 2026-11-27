import { test } from 'node:test'
import assert from 'node:assert/strict'
import { matchesSearch } from '../lib/search.js'
import { compareValues } from '../lib/sort.js'
import { weekMeta } from '../lib/isoWeek.js'
import { parseDager } from '../lib/parseDager.js'
import { pivotIfNeeded, normalizeRetailerKey } from '../lib/pivot.js'
import { deriveRetailers } from '../lib/retailers.js'
import { fetchAllRows } from '../lib/fetchAllRows.js'
import { buildWeekly } from '../lib/ukesnitt.js'
import { branchArgs } from '../lib/branchArgs.js'
import {
  NO_FILTER, setLevel, matchesLevels, levelOptions, categoryPath, isSunCare,
} from '../lib/categories.js'

test('matchesSearch matches product, brand and item number', () => {
  const row = { produkt: 'Paracet 500 mg', merke: 'Karo', varenummer: 123456 }
  assert.equal(matchesSearch(row, 'paracet'), true)
  assert.equal(matchesSearch(row, '  KARO '), true)
  assert.equal(matchesSearch(row, '3456'), true)
  assert.equal(matchesSearch(row, 'ibux'), false)
  assert.equal(matchesSearch(row, ''), true)
  assert.equal(matchesSearch({ produkt: null }, 'x'), false)
})

test('compareValues puts missing values last in both directions', () => {
  const sort = dir => [3, null, 1, undefined, 2].sort((a, b) => compareValues(a, b, dir))
  assert.deepEqual(sort('asc').slice(0, 3), [1, 2, 3])
  assert.deepEqual(sort('desc').slice(0, 3), [3, 2, 1])
})

test('compareValues sorts text by Norwegian alphabet', () => {
  const sorted = ['Østerbro', 'Zalo', 'Ære', 'apotek', 'Åsane'].sort((a, b) => compareValues(a, b))
  assert.deepEqual(sorted, ['apotek', 'Zalo', 'Ære', 'Østerbro', 'Åsane'])
  assert.equal(compareValues('a', null), -1)
  assert.equal(compareValues('b', 'a', 'desc') < 0, true)
})

test('weekMeta follows ISO-8601 across year boundaries', () => {
  assert.deepEqual(weekMeta('2026-01-01'), { key: '2026-W01', week: 1, year: 2026, monday: '2025-12-29' })
  assert.equal(weekMeta('2021-01-03').key, '2020-W53')
  assert.equal(weekMeta('2024-12-30').key, '2025-W01')
  assert.equal(weekMeta('not a date'), null)
})

test('parseDager falls back on invalid input and keeps 0 as "all"', () => {
  assert.equal(parseDager(null, 30), 30)
  assert.equal(parseDager('abc', 30), 30)
  assert.equal(parseDager('-5', 30), 30)
  assert.equal(parseDager('0', 30), 0)
  assert.equal(parseDager('90', 30), 90)
  assert.equal(parseDager('999999', 30), 3650)
})

test('pivotIfNeeded turns long rows into one row per date and product', () => {
  const rows = [
    { dato: '2026-01-02T03:00:00', varenummer: '1', produkt: 'A', kilde: 'Apotek 1', pris: '10.5' },
    { dato: '2026-01-02T03:00:00', varenummer: '1', produkt: 'A', kilde: 'Boots', pris: 12 },
    { dato: '2026-01-01', varenummer: '1', produkt: 'A', kilde: 'Vitus Apotek', pris: 11 },
  ]
  assert.deepEqual(pivotIfNeeded(rows), [
    { dato: '2026-01-01', varenummer: '1', produkt: 'A', kategori: undefined, merke: undefined, vitusapotek: 11 },
    { dato: '2026-01-02', varenummer: '1', produkt: 'A', kategori: undefined, merke: undefined, apotek1: 10.5, boots: 12 },
  ])
  const wide = [{ dato: '2026-01-01', boots: 1 }]
  assert.equal(pivotIfNeeded(wide), wide)
  assert.equal(normalizeRetailerKey(' Farmasiet.no '), 'farmasiet')
})

test('deriveRetailers finds price columns and applies known styles', () => {
  const retailers = deriveRetailers([
    { id: 1, produkt: 'A', laveste_pris: 5, boots: 10, apotek1: null },
    { id: 2, produkt: 'B', apotek1: 12, ny_kjede: 9 },
  ])
  assert.deepEqual(retailers.map(r => r.key), ['boots', 'apotek1', 'ny_kjede'])
  assert.equal(retailers[1].label, 'Apotek 1')
  assert.equal(retailers[2].label, 'Ny kjede')
  assert.deepEqual(deriveRetailers([]), [])
})

// Etterligner en Supabase-spørring: .range() gir én side, med totalt antall
// når `withCount` er satt (som select(..., { count: 'exact' })).
function fakeTable(all, { withCount = true, failAt = null } = {}) {
  const calls = []
  let active = 0
  let peak = 0
  const buildQuery = () => ({
    range: async (from, to) => {
      calls.push([from, to])
      peak = Math.max(peak, ++active)
      await new Promise(resolve => setTimeout(resolve, 2))
      active--
      if (from === failAt) return { data: null, error: { message: 'boom' } }
      return { data: all.slice(from, to + 1), error: null, count: withCount ? all.length : null }
    },
  })
  return { buildQuery, calls, peak: () => peak }
}

test('fetchAllRows fetches the remaining pages in parallel and keeps row order', async () => {
  const all = Array.from({ length: 12500 }, (_, i) => i)
  const table = fakeTable(all)
  const { data, error } = await fetchAllRows(table.buildQuery, { concurrency: 4 })
  assert.equal(error, null)
  assert.deepEqual(data, all)
  assert.equal(table.calls.length, 13)
  assert.equal(table.peak(), 4)
})

test('fetchAllRows makes a single request when everything fits on one page', async () => {
  const table = fakeTable([1, 2, 3])
  assert.deepEqual(await fetchAllRows(table.buildQuery), { data: [1, 2, 3], error: null })
  assert.deepEqual(table.calls, [[0, 999]])
  // Nøyaktig én full side: antallet viser at det ikke finnes flere
  const exact = fakeTable(Array.from({ length: 1000 }, (_, i) => i))
  assert.equal((await fetchAllRows(exact.buildQuery)).data.length, 1000)
  assert.equal(exact.calls.length, 1)
})

test('fetchAllRows pages one by one when the query has no count', async () => {
  const all = Array.from({ length: 2500 }, (_, i) => i)
  const table = fakeTable(all, { withCount: false })
  const { data, error } = await fetchAllRows(table.buildQuery)
  assert.equal(error, null)
  assert.deepEqual(data, all)
  assert.deepEqual(table.calls, [[0, 999], [1000, 1999], [2000, 2999]])
  assert.equal(table.peak(), 1)
})

test('fetchAllRows surfaces errors from any page', async () => {
  const all = Array.from({ length: 5000 }, (_, i) => i)
  assert.deepEqual(await fetchAllRows(fakeTable(all, { failAt: 0 }).buildQuery), { data: null, error: { message: 'boom' } })
  assert.deepEqual(await fetchAllRows(fakeTable(all, { failAt: 3000 }).buildQuery), { data: null, error: { message: 'boom' } })
})

test('pivotIfNeeded ignores zero prices (retailer does not stock the product)', () => {
  const rows = [
    { dato: '2026-01-01', varenummer: '1', kilde: 'Boots', pris: 0 },
    { dato: '2026-01-01', varenummer: '1', kilde: 'Apotek 1', pris: 99 },
  ]
  const [row] = pivotIfNeeded(rows)
  assert.equal(row.apotek1, 99)
  assert.equal('boots' in row, false)
})

test('buildWeekly turns per-product weekly averages into table data', () => {
  const { weeks, rows, retailers } = buildWeekly([
    {
      varenummer: '003051', produkt: 'Panodil', merke: 'PANODIL', kategori: 'Paracetamol',
      uker: {
        '2026-11-09': { oda: 30, apotek1: 39.9, boots: null },
        '2026-11-16': { apotek1: '41.50', farmasiet: 38 },
      },
    },
    { varenummer: '017833', produkt: null, merke: null, kategori: null, uker: {} },
  ])
  assert.deepEqual(weeks.map(w => w.key), ['2026-W47', '2026-W46'])
  assert.equal(weeks[0].monday, '2026-11-16')
  // Kjente kjeder først i fast rekkefølge, deretter resten alfabetisk
  assert.deepEqual(retailers.map(r => r.key), ['farmasiet', 'apotek1', 'oda'])
  assert.deepEqual(rows[0].weeks['2026-W46'], { oda: 30, apotek1: 39.9 })
  assert.equal(rows[0].weeks['2026-W47'].apotek1, 41.5)
  assert.deepEqual(rows[1], { vn: '017833', produkt: '017833', merke: '', kategori: '', niva1: '', niva2: '', weeks: {} })
})

test('buildWeekly tolerates a missing or malformed response', () => {
  assert.deepEqual(buildWeekly(null), { weeks: [], rows: [], retailers: [] })
  assert.deepEqual(buildWeekly({ error: 'x' }), { weeks: [], rows: [], retailers: [] })
})

// --- kategoritreet ---------------------------------------------------------

const TREE = [
  { id: 1, kategori: 'Hudpleie', niva1: 'Body', niva2: 'Hand care' },
  { id: 2, kategori: 'Hudpleie', niva1: 'Body', niva2: 'Deodorants' },
  { id: 3, kategori: 'Hudpleie', niva1: 'Sun & tan', niva2: 'After sun' },
  { id: 4, kategori: 'Smerte', niva1: 'Topical pain (M02A)', niva2: null },
  { id: 5, kategori: 'Munnpleie' },
]

test('levelOptions: undernivåene følger det som er valgt over', () => {
  assert.deepEqual(levelOptions(TREE, NO_FILTER), {
    kategori: ['Hudpleie', 'Munnpleie', 'Smerte'], niva1: [], niva2: [],
  })
  const body = setLevel(setLevel(NO_FILTER, 'kategori', 'Hudpleie'), 'niva1', 'Body')
  assert.deepEqual(levelOptions(TREE, body), {
    kategori: ['Hudpleie', 'Munnpleie', 'Smerte'],
    niva1: ['Body', 'Sun & tan'],
    niva2: ['Deodorants', 'Hand care'],
  })
  // Produkter uten undernivåer (før migreringen) gir ingen valg, ikke tomme valg
  assert.deepEqual(levelOptions(TREE, setLevel(NO_FILTER, 'kategori', 'Munnpleie')).niva1, [])
})

test('setLevel nullstiller nivåene under', () => {
  const deep = { kategori: 'Hudpleie', niva1: 'Body', niva2: 'Hand care' }
  assert.deepEqual(setLevel(deep, 'niva1', 'Sun & tan'), { kategori: 'Hudpleie', niva1: 'Sun & tan', niva2: 'alle' })
  assert.deepEqual(setLevel(deep, 'kategori', 'Smerte'), { kategori: 'Smerte', niva1: 'alle', niva2: 'alle' })
  assert.deepEqual(setLevel(deep, 'niva2', ''), { kategori: 'Hudpleie', niva1: 'Body', niva2: 'alle' })
})

test('matchesLevels filtrerer på alle valgte nivåer', () => {
  const ids = f => TREE.filter(r => matchesLevels(r, f)).map(r => r.id)
  assert.deepEqual(ids(NO_FILTER), [1, 2, 3, 4, 5])
  assert.deepEqual(ids({ kategori: 'Hudpleie', niva1: 'alle', niva2: 'alle' }), [1, 2, 3])
  assert.deepEqual(ids({ kategori: 'Hudpleie', niva1: 'Body', niva2: 'Hand care' }), [1])
})

test('categoryPath og isSunCare', () => {
  assert.equal(categoryPath(TREE[0]), 'Body › Hand care')
  assert.equal(categoryPath(TREE[3]), 'Topical pain (M02A)')
  assert.equal(categoryPath(TREE[4]), '')
  assert.deepEqual(TREE.filter(isSunCare).map(r => r.id), [3])
  assert.equal(isSunCare({ kategori: 'Solkrem' }), true)
  assert.equal(isSunCare({ kategori: 'Hudpleie', niva1: 'Face' }), false)
})

test('undernivåene regnes ikke som kjeder', () => {
  const rows = [{ id: 1, produkt: 'A', kategori: 'Smerte', niva1: '2024', niva2: 'x', niva3: null, segment: 'Karo', boots: 10 }]
  assert.deepEqual(deriveRetailers(rows).map(r => r.key), ['boots'])
})

test('branchArgs: gren av kategoritreet fra spørringen', () => {
  const args = q => branchArgs(new URLSearchParams(q))
  assert.deepEqual(args('dager=30'), {})
  assert.deepEqual(args('kategori=alle&niva1=Body'), {})
  assert.deepEqual(args('kategori=Hudpleie'), { under_kategori: 'Hudpleie' })
  assert.deepEqual(args('kategori=Hudpleie&niva1=Sun+%26+tan'), { under_kategori: 'Hudpleie', under_niva1: 'Sun & tan' })
  assert.deepEqual(args('kategori=Hudpleie&niva1=alle'), { under_kategori: 'Hudpleie' })
})

import {
  median, productPrices, groupKeyFor, retailerIndex, indexMatrix, segmentLadder, spreadSummary,
} from '../lib/insights.js'

const KEYS = ['a', 'b', 'c']

test('productPrices indexes each retailer against the product mean', () => {
  const p = productPrices({ a: 90, b: '110', c: null }, KEYS)
  assert.equal(p.snitt, 100)
  assert.deepEqual(Object.keys(p.index), ['a', 'b'])
  assert.equal(Math.round(p.index.a), 90)
  assert.equal(Math.round(p.index.b), 110)
  assert.equal(productPrices({ a: 50, b: 0 }, KEYS).index, null) // 0 kr is not a price
  assert.equal(productPrices({ a: null }, KEYS), null)
})

test('retailerIndex compares like for like, not average shelf price', () => {
  // b only stocks the expensive product but is the cheaper chain on it
  const rows = [{ a: 10, c: 10 }, { a: 220, b: 180 }]
  const index = retailerIndex(rows, KEYS)
  assert.deepEqual(index.map(d => d.key), ['b', 'c', 'a'])
  assert.equal(index[0].index, 90)
  assert.equal(index[0].antall, 1)
  assert.equal(index[2].index, 105)
  assert.deepEqual(retailerIndex([{ a: 10 }], KEYS), [])
})

test('indexMatrix groups by the given level and skips ungrouped products', () => {
  const rows = [
    { kategori: 'Hud', a: 90, b: 110 },
    { kategori: 'Hud', a: 80, b: 120 },
    { kategori: 'Fot', a: 100, b: 100 },
    { kategori: null, a: 1, b: 2 },
    { kategori: 'Fot', a: 5 },
  ]
  const m = indexMatrix(rows, KEYS, 'kategori')
  assert.deepEqual(m.map(g => [g.gruppe, g.antall]), [['Hud', 2], ['Fot', 1]])
  assert.deepEqual(m[0].celler.a, { index: 85, antall: 2 })
})

test('segmentLadder needs enough products in two segments', () => {
  const mk = (segment, pris) => ({ kategori: 'Hud', segment, a: pris })
  const rows = [
    ...[100, 120, 140].map(p => mk('Karo', p)),
    ...[40, 60, 80].map(p => mk('Egne merker', p)),
    mk('Andre', 500), // too few to count as a segment, still part of the group
    { kategori: 'Fot', segment: 'Karo', a: 10 },
  ]
  const [hud, ...rest] = segmentLadder(rows, KEYS, 'kategori')
  assert.equal(rest.length, 0)
  assert.equal(hud.median, 100)
  assert.deepEqual(Object.keys(hud.segmenter), ['Karo', 'Egne merker'])
  assert.equal(Math.round(hud.segmenter.Karo.avvik), 20)
  assert.equal(Math.round(hud.segmenter['Egne merker'].avvik), -40)
})

test('spreadSummary, median and groupKeyFor', () => {
  assert.equal(median([3, 1, 2]), 2)
  assert.equal(median([4, 1, 2, 3]), 2.5)
  assert.equal(median([]), null)
  const s = spreadSummary([{ a: 100, b: 150 }, { a: 100, b: 110 }, { a: 100, b: 130 }, { a: 7 }], KEYS)
  assert.equal(s.antall, 3)
  assert.equal(Math.round(s.medianPct), 30)
  assert.equal(groupKeyFor(NO_FILTER), 'kategori')
  assert.equal(groupKeyFor(setLevel(NO_FILTER, 'kategori', 'Hud')), 'niva1')
  assert.equal(groupKeyFor({ kategori: 'Hud', niva1: 'Body', niva2: 'alle' }), 'niva2')
  assert.equal(groupKeyFor({ kategori: 'Hud', niva1: 'Body', niva2: 'Hand' }), 'niva3')
})
