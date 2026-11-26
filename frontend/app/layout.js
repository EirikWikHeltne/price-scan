import { Figtree } from 'next/font/google'
import './globals.css'

// Karos profilfont er Euclid Circular A (se --font-body i globals.css). Den er
// lisensiert og ligger ikke i repoet, så den vises foreløpig bare på maskiner
// der den er installert. Figtree er reserven for alle andre, og ligger sammen
// med resten av appen (next/font) slik at siden ikke må vente på et eget kall
// til Google Fonts før tekst vises.
const fallbackFont = Figtree({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  style: ['normal', 'italic'],
  display: 'swap',
  variable: '--font-fallback',
})

export const metadata = {
  title: 'PrisScanner — Sammenlign apotekpriser',
  description: 'Sammenlign apotekpriser på tvers av norske apotek.',
  icons: {
    icon: '/logo.svg',
    apple: '/logo.svg',
  },
  openGraph: {
    title: 'PrisScanner — Sammenlign apotekpriser',
    description: 'Sammenlign apotekpriser på tvers av norske apotek.',
    images: [{ url: '/og-image.png', width: 1200, height: 630 }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'PrisScanner — Sammenlign apotekpriser',
    description: 'Sammenlign apotekpriser på tvers av norske apotek.',
    images: ['/og-image.png'],
  },
}

export default function RootLayout({ children }) {
  return (
    <html lang="nb" className={fallbackFont.variable}>
      <head>
        <meta name="theme-color" content="#110B36" />
      </head>
      <body>{children}</body>
    </html>
  )
}
