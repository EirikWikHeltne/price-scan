export default function Footer({ left, right = 'Oppdateres daglig kl. 03:00' }) {
  return (
    <footer className="footer">
      <span>{left ?? 'Karo Healthcare Norway \u00b7 Prisdata fra Farmasiet, Boots, Vitusapotek, Apotek 1'}</span>
      <span>{right}</span>
    </footer>
  )
}
