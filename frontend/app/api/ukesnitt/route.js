import { respondWithRpc } from '@/lib/rpcJson'

export const dynamic = 'force-dynamic'

// Én rad per produkt med ukesnitt per kjede:
// { varenummer, produkt, merke, kategori, niva1, niva2, niva3,
//   uker: { '<mandag>': { <kjede>: snitt } } }
// ?kategori= og ?niva1= avgrenser til en gren av kategoritreet. Hele
// produktlisten over mange uker blir for stor til å sende i ett svar.
export async function GET(request) {
  return respondWithRpc(request, 'ukesnitt', 84, { unfilteredFallback: true })
}
