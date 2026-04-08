import os
from datetime import datetime, timedelta, timezone
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
_client = None

def get_client():
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise EnvironmentError(
                "Missing required environment variables: SUPABASE_URL and SUPABASE_SERVICE_KEY"
            )
        _client = create_client(url, key)
    return _client

def get_active_products():
    return get_client().table("produkter").select("*").eq("aktiv", True).execute().data

def save_resolved_url(varenummer: str, butikk: str, url: str):
    get_client().table("produkter").update(
        {f"url_{butikk}": url}
    ).eq("varenummer", varenummer).execute()

def bulk_insert_prices(rows: list[dict]):
    if rows:
        get_client().table("priser").insert(rows).execute()

def get_prishistorikk(
    produkt_id: int,
    dager: int | None = None,
    fra_dato: str | None = None,
    til_dato: str | None = None,
    butikk: str | None = None,
) -> list[dict]:
    query = (
        get_client()
        .table("prishistorikk")
        .select("*")
        .eq("produkt_id", produkt_id)
    )

    if butikk:
        query = query.eq("butikk", butikk)

    if fra_dato:
        query = query.gte("dato", fra_dato)
    elif dager:
        start = (datetime.now(timezone.utc) - timedelta(days=dager)).strftime("%Y-%m-%d")
        query = query.gte("dato", start)

    if til_dato:
        query = query.lte("dato", til_dato)

    query = query.order("scraped_at", desc=True)

    return query.execute().data
