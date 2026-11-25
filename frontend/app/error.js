'use client'
import { useEffect } from 'react'

export default function GlobalError({ error, reset }) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div className="app">
      <div className="empty" style={{ padding: '4rem' }}>
        <div className="empty-icon">&#9888;</div>
        <div className="empty-text">Noe gikk galt</div>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: '0.75rem', maxWidth: 420, textAlign: 'center' }}>
          En uventet feil oppstod. Prøv å laste siden på nytt.
        </p>
        <button className="tab active" style={{ marginTop: '1.25rem' }} onClick={() => reset()}>
          Prøv igjen
        </button>
      </div>
    </div>
  )
}
