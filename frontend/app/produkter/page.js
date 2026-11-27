'use client'
import { useState, useEffect, useMemo, useCallback, useDeferredValue } from 'react'
import Header from '@/components/Header'
import Footer from '@/components/Footer'
import { TableSkeleton } from '@/components/Skeleton'
import { fetchJson } from '@/lib/fetchJson'
import CategoryFilter from '@/components/CategoryFilter'
import ShowMore, { ROW_STEP } from '@/components/ShowMore'
import { CAT_CLASS, NO_FILTER, matchesLevels, categoryPath } from '@/lib/categories'
import { fmtDate } from '@/lib/format'
import { matchesSearch } from '@/lib/search'
import { compareValues } from '@/lib/sort'

export default function ProdukterPage() {
  const [data, setData]         = useState([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)
  const [search, setSearch]     = useState('')
  const deferredSearch = useDeferredValue(search)
  const [cat, setCat]           = useState(NO_FILTER)
  const [rowLimit, setRowLimit] = useState(ROW_STEP)
  const [sortCol, setSortCol]   = useState('kategori')
  const [sortDir, setSortDir]   = useState('asc')

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const json = await fetchJson('/api/produkter')
      setData(Array.isArray(json) ? json : [])
    } catch (e) {
      console.error(e)
      setError('Kunne ikke hente produkter. Prøv igjen.')
    }
    setLoading(false)
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const categories = useMemo(() => {
    return [...new Set(data.map(r => r.kategori).filter(Boolean))].sort()
  }, [data])

  const brands = useMemo(() => {
    return [...new Set(data.map(r => r.merke).filter(Boolean))].sort()
  }, [data])

  const filtered = useMemo(() => {
    let d = data
    d = d.filter(r => matchesLevels(r, cat))
    if (deferredSearch.trim()) d = d.filter(r => matchesSearch(r, deferredSearch))
    return [...d].sort((a, b) => compareValues(a[sortCol], b[sortCol], sortDir))
  }, [data, cat, deferredSearch, sortCol, sortDir])

  // Stats by category
  const categoryStats = useMemo(() => {
    const stats = {}
    data.forEach(r => {
      if (!r.kategori) return
      if (!stats[r.kategori]) stats[r.kategori] = { count: 0, brands: new Set() }
      stats[r.kategori].count++
      if (r.merke) stats[r.kategori].brands.add(r.merke)
    })
    return stats
  }, [data])

  function handleSort(col) {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(col); setSortDir('asc') }
  }

  const renderSortIcon = (col) => {
    if (sortCol !== col) return <span style={{ opacity: 0.3 }}>&#8597;</span>
    return <span>{sortDir === 'asc' ? '\u2191' : '\u2193'}</span>
  }

  async function downloadExcel() {
    // Lazy-load xlsx så det store biblioteket holdes ute av siden til det trengs
    const XLSX = await import('xlsx')
    const rows = filtered.map(row => ({
      Produkt: row.produkt,
      Merke: row.merke,
      Varenummer: row.varenummer,
      Kategori: row.kategori,
      'Nivå 1': row.niva1 ?? null,
      'Nivå 2': row.niva2 ?? null,
      'Nivå 3': row.niva3 ?? null,
      Segment: row.segment ?? null,
      'Sist oppdatert': row.sist_oppdatert
        ? new Date(row.sist_oppdatert).toLocaleDateString('nb-NO')
        : '',
    }))
    const ws = XLSX.utils.json_to_sheet(rows)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Produkter')
    XLSX.writeFile(wb, `karo-produkter-${new Date().toISOString().slice(0, 10)}.xlsx`)
  }

  return (
    <div className="app">
      <Header active="/produkter" showLastUpdated={false} />

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
        <CategoryFilter rows={data} value={cat} onChange={setCat} />
        <div className="controls-right">
          <span className="count-badge">{filtered.length} produkter</span>
          <button
            className="btn-excel"
            onClick={downloadExcel}
            disabled={!filtered.length}
          >
            Last ned Excel
          </button>
        </div>
      </div>

      {/* Category summary cards */}
      {!loading && data.length > 0 && (
        <div className="stats-bar">
          <div className="stat">
            <span className="stat-label">Totalt produkter</span>
            <span className="stat-value">{data.length}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Kategorier</span>
            <span className="stat-value">{categories.length}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Merker</span>
            <span className="stat-value">{brands.length}</span>
          </div>
          {Object.entries(categoryStats).sort(([a], [b]) => a.localeCompare(b)).map(([cat, s]) => (
            <div key={cat} className="stat">
              <span className="stat-label">{cat}</span>
              <span className="stat-value">{s.count}</span>
              <span className="stat-sub">{s.brands.size} merker</span>
            </div>
          ))}
        </div>
      )}

      <div className="table-wrap">
        {loading ? (
          <TableSkeleton cols={5} label="Henter produkter..." />
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
          <table>
            <thead>
              <tr>
                <th onClick={() => handleSort('varenummer')} className={sortCol === 'varenummer' ? 'sorted' : ''} style={{ width: '120px' }}>
                  Varenummer {renderSortIcon('varenummer')}
                </th>
                <th onClick={() => handleSort('produkt')} className={sortCol === 'produkt' ? 'sorted' : ''}>
                  Produkt {renderSortIcon('produkt')}
                </th>
                <th onClick={() => handleSort('merke')} className={sortCol === 'merke' ? 'sorted' : ''} style={{ width: '160px' }}>
                  Merke {renderSortIcon('merke')}
                </th>
                <th onClick={() => handleSort('kategori')} className={sortCol === 'kategori' ? 'sorted' : ''} style={{ width: '220px' }}>
                  Kategori {renderSortIcon('kategori')}
                </th>
                <th style={{ width: '140px' }}>Sist oppdatert</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, rowLimit).map(row => (
                <tr key={row.id}>
                  <td>
                    <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                      {row.varenummer || '—'}
                    </span>
                  </td>
                  <td>
                    <span className="product-name">{row.produkt}</span>
                  </td>
                  <td>
                    <span style={{ fontSize: '0.78rem' }}>{row.merke || '—'}</span>
                  </td>
                  <td className="td-category">
                    <span className={`cat-pill ${CAT_CLASS[row.kategori] || ''}`}>
                      {row.kategori}
                    </span>
                    {categoryPath(row) && <div className="cat-path">{categoryPath(row)}</div>}
                  </td>
                  <td>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      {row.sist_oppdatert
                        ? fmtDate(row.sist_oppdatert)
                        : '—'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {!loading && !error && (
          <ShowMore
            shown={Math.min(rowLimit, filtered.length)}
            total={filtered.length}
            onMore={() => setRowLimit(n => n + ROW_STEP)}
            onAll={() => setRowLimit(Infinity)}
          />
        )}
      </div>

      <Footer left={'Karo Healthcare Norway \u00b7 Produkter som overvåkes'} />
    </div>
  )
}
