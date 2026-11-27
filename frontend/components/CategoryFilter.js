'use client'
import { useMemo } from 'react'
import { ALL, levelOptions, setLevel } from '@/lib/categories'

// Kategorifaner med nedtrekkslister for undernivåene til valgt kategori.
// `rows` er produktene valgene skal hentes fra; `value` er
// { kategori, niva1, niva2 } (se NO_FILTER i lib/categories). `levels={2}`
// skjuler listen for nivå 2; `allowAll={false}` fjerner «Alle kategorier».
export default function CategoryFilter({ rows, value, onChange, allowAll = true, levels = 3 }) {
  const options = useMemo(() => levelOptions(rows, value), [rows, value])
  const tabs = allowAll ? [ALL, ...options.kategori] : options.kategori

  return (
    <>
      <div className="filter-tabs">
        {tabs.map(k => (
          <button
            key={k}
            className={`tab ${value.kategori === k ? 'active' : ''}`}
            onClick={() => onChange(setLevel(value, 'kategori', k))}
          >
            {k === ALL ? 'Alle kategorier' : k}
          </button>
        ))}
      </div>
      {options.niva1.length > 0 && (
        <select
          className="brand-select"
          aria-label="Nivå 1"
          value={value.niva1}
          onChange={e => onChange(setLevel(value, 'niva1', e.target.value))}
        >
          <option value={ALL}>Nivå 1: alle</option>
          {options.niva1.map(n => <option key={n} value={n}>{n}</option>)}
        </select>
      )}
      {levels > 2 && options.niva2.length > 0 && (
        <select
          className="brand-select"
          aria-label="Nivå 2"
          value={value.niva2}
          onChange={e => onChange(setLevel(value, 'niva2', e.target.value))}
        >
          <option value={ALL}>Nivå 2: alle</option>
          {options.niva2.map(n => <option key={n} value={n}>{n}</option>)}
        </select>
      )}
    </>
  )
}
