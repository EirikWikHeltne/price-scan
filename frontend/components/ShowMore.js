'use client'

// Lange tabeller tegnes i bolker: flere tusen rader på én gang gjør siden
// treg å åpne og å filtrere i. `shown` av `total` rader vises nå.
export const ROW_STEP = 300

export default function ShowMore({ shown, total, onMore, onAll }) {
  if (shown >= total) return null
  return (
    <div className="show-more">
      <span>Viser {shown} av {total}</span>
      <button className="tab" onClick={onMore}>Vis {Math.min(ROW_STEP, total - shown)} til</button>
      <button className="tab" onClick={onAll}>Vis alle</button>
    </div>
  )
}
