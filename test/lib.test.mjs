import { test } from 'node:test'
import assert from 'node:assert/strict'
import { matchesSearch } from '../lib/search.js'
import { compareValues } from '../lib/sort.js'
import { weekMeta } from '../lib/isoWeek.js'
import { parseDager } from '../lib/parseDager.js'
import { pivotIfNeeded, normalizeRetailerKey } from '../lib/pivot.js'
import { deriveRetailers } from '../lib/retailers.js'
import { fetchAllRows } from '../lib/fetchAllRows.js'
import { aggregateWeekly } from '../lib/weekly.js'

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

test('aggregateWeekly averages each retailer per product and ISO week', () => {
  const rows = [
    { dato: '2026-01-05', varenummer: '1', produkt: 'A', kategori: 'K', merke: 'M', boots: 10, apotek1: 20 },
    { dato: '2026-01-07', varenummer: '1', produkt: 'A', kategori: 'K', merke: 'M', boots: 13 },
    { dato: '2026-01-12', varenummer: '1', produkt: 'A', kategori: 'K', merke: 'M', boots: 30 },
    { dato: '2026-01-06', varenummer: '2', produkt: 'B', apotek1: 5 },
  ]
  assert.deepEqual(aggregateWeekly(rows), [
    { dato: '2026-01-05', varenummer: '1', produkt: 'A', kategori: 'K', merke: 'M', boots: 11.5, apotek1: 20 },
    { dato: '2026-01-05', varenummer: '2', produkt: 'B', kategori: undefined, merke: undefined, apotek1: 5 },
    { dato: '2026-01-12', varenummer: '1', produkt: 'A', kategori: 'K', merke: 'M', boots: 30 },
  ])
})
