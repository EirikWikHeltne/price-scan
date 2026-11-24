import { respondWithRpc } from '@/lib/rpcJson'

export const dynamic = 'force-dynamic'

// Én rad per produkt med ukesnitt per kjede:
// { varenummer, produkt, merke, kategori, uker: { '<mandag>': { <kjede>: snitt } } }
export async function GET(request) {
  return respondWithRpc(request, 'ukesnitt', 84)
}
