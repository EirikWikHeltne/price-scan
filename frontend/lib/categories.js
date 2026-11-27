// Kategoritreet: kategori › nivå 1 › nivå 2 (› nivå 3). `kategori` er
// toppnivået; undernivåene kan mangle på et produkt.

export const CAT_CLASS = {
  'Hudpleie':     'cat-hud',
  'Fotpleie':     'cat-fot',
  'Munnpleie':    'cat-munn',
  'Intimpleie':   'cat-intim',
  'Mage og tarm': 'cat-mage',
  'Smerte':       'cat-smerte',
}

export const ALL = 'alle'
export const NO_FILTER = Object.freeze({ kategori: ALL, niva1: ALL, niva2: ALL })

const LEVELS = ['kategori', 'niva1', 'niva2']

// Nytt filter med `level` satt til `value`. Nivåene under nullstilles, siden
// de hører til den forrige grenen.
export function setLevel(filter, level, value) {
  const next = { ...NO_FILTER, ...filter }
  const depth = LEVELS.indexOf(level)
  LEVELS.forEach((l, i) => {
    if (i === depth) next[l] = value || ALL
    else if (i > depth) next[l] = ALL
  })
  return next
}

export function matchesLevels(row, filter) {
  if (!filter) return true
  return LEVELS.every(l => !filter[l] || filter[l] === ALL || row?.[l] === filter[l])
}

const distinct = (rows, key) =>
  [...new Set(rows.map(r => r?.[key]).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'nb'))

// Valgene som skal vises for hvert nivå, gitt det som er valgt over.
export function levelOptions(rows, filter = NO_FILTER) {
  const list = Array.isArray(rows) ? rows : []
  const inKategori = filter.kategori === ALL ? [] : list.filter(r => r.kategori === filter.kategori)
  const inNiva1 = filter.niva1 === ALL ? [] : inKategori.filter(r => r.niva1 === filter.niva1)
  return {
    kategori: distinct(list, 'kategori'),
    niva1: distinct(inKategori, 'niva1'),
    niva2: distinct(inNiva1, 'niva2'),
  }
}

// «Body › Hand care» til visning under kategorien.
export function categoryPath(row) {
  return [row?.niva1, row?.niva2].filter(Boolean).join(' › ')
}

// Solpleie ligger som en gruppe under Hudpleie («Sun & tan»). Kategorinavn
// med «sol»/«sun» regnes også med.
export function isSunCare(row) {
  return [row?.kategori, row?.niva1].some(v => typeof v === 'string' && /\b(sol|sun)/i.test(v))
}
