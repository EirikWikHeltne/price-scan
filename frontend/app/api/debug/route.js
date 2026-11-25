import { getSupabase } from '@/lib/supabaseServer'

export const dynamic = 'force-dynamic'

export async function GET() {
  if (process.env.NODE_ENV !== 'development') {
    return Response.json({ error: 'Not available in production' }, { status: 404 })
  }

  const info = {
    env: {
      url: process.env.NEXT_PUBLIC_SUPABASE_URL ? 'set' : 'MISSING',
      serviceKey: process.env.SUPABASE_SERVICE_ROLE_KEY ? 'set' : 'MISSING',
    }
  }

  if (!process.env.NEXT_PUBLIC_SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
    return Response.json(info)
  }

  const { count, error: tablesError } = await getSupabase()
    .from('prissammenligning')
    .select('*', { count: 'exact', head: true })

  info.tableCheck = {
    totalRows: count,
    error: tablesError?.message || null,
    errorCode: tablesError?.code || null,
  }

  return Response.json(info)
}
