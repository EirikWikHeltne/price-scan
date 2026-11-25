'use client'
import { useState } from 'react'
import Link from 'next/link'

const NAV_ITEMS = [
  { href: '/',                    label: 'Tabell' },
  { href: '/historikk',           label: 'Historikk' },
  { href: '/ukesnitt',            label: 'Ukesnitt' },
  { href: '/kategori-historikk',  label: 'Kategoritrend' },
  { href: '/solpleie',            label: 'Solpleie' },
  { href: '/grafer',              label: 'Grafer' },
  { href: '/produkter',           label: 'Produkter' },
  { href: '/sammenlign',          label: 'Sammenlign' },
]

function formatUpdated(date) {
  if (!date) return null
  if (isNaN(date)) return null
  // Bare dato: kilden er en ren dato uten klokkeslett, så et klokkeslett her
  // ville vært oppdiktet.
  return date.toLocaleDateString('nb-NO', { day: 'numeric', month: 'short', year: 'numeric' })
}

export default function Header({ active, lastUpdated, showLastUpdated = true }) {
  const [mobileNav, setMobileNav] = useState(false)
  const updatedLabel = formatUpdated(lastUpdated)

  return (
    <header className="header">
      <div className="header-left">
        <div className="header-logo">Karo <span className="header-logo-accent">Priser</span></div>
        <div className="header-sub">Prisovervåking</div>
      </div>
      {showLastUpdated && updatedLabel && (
        <div className="header-meta-mobile">
          <span className="header-dot"></span>
          {`Oppdatert ${updatedLabel}`}
        </div>
      )}
      <button
        className={`mobile-nav-toggle ${mobileNav ? 'open' : ''}`}
        onClick={() => setMobileNav(v => !v)}
        aria-label="Meny"
        aria-expanded={mobileNav}
        aria-controls="main-nav"
      >
        <span></span><span></span><span></span>
      </button>
      <div id="main-nav" className={`header-right ${mobileNav ? 'open' : ''}`}>
        <nav className="header-nav" aria-label="Hovedmeny">
          {NAV_ITEMS.map(item => (
            item.href === active ? (
              <span key={item.href} className="nav-link active" aria-current="page">{item.label}</span>
            ) : (
              <Link
                key={item.href}
                href={item.href}
                className="nav-link"
                onClick={() => setMobileNav(false)}
              >
                {item.label}
              </Link>
            )
          ))}
        </nav>
        {showLastUpdated && (
          <div className="header-meta">
            <span className="header-dot"></span>
            {updatedLabel ? `Oppdatert ${updatedLabel}` : 'Laster...'}
          </div>
        )}
      </div>
    </header>
  )
}
