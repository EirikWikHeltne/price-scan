import { respondWithRpc } from '@/lib/rpcJson'

export const dynamic = 'force-dynamic'

// Én rad per (dato, kategori) med snittpris per kjede, `snitt` (snitt av
// kjedesnittene) og `antall` produkter med pris.
export async function GET(request) {
  return respondWithRpc(request, 'kategori_historikk', 90)
}
