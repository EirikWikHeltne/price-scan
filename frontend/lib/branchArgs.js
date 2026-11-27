// ?kategori= og ?niva1= velger en gren av kategoritreet. Tomme verdier og
// «alle» betyr ingen avgrensning.
export function branchArgs(searchParams) {
  const args = {}
  const kategori = searchParams.get('kategori')
  const niva1 = searchParams.get('niva1')
  if (kategori && kategori !== 'alle') {
    args.under_kategori = kategori
    if (niva1 && niva1 !== 'alle') args.under_niva1 = niva1
  }
  return args
}
