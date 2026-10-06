import os
import time
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

_PAGE = 1000  # PostgREST's default max-rows; larger responses are silently truncated

def get_active_products():
    """Return all active products, paging past the server's row cap."""
    products = []
    while True:
        page = (
            get_client().table("produkter").select("*").eq("aktiv", True)
            .order("id").range(len(products), len(products) + _PAGE - 1)
            .execute().data
        )
        products.extend(page)
        if len(page) < _PAGE:
            return products

def save_resolved_url(varenummer: str, butikk: str, url: str):
    get_client().table("produkter").update(
        {f"url_{butikk}": url}
    ).eq("varenummer", varenummer).execute()

_INSERT_CHUNK = 500
_INSERT_RETRIES = 3

def bulk_insert_prices(rows: list[dict]):
    """Insert price rows in chunks, retrying each chunk on transient errors.

    These rows represent hours of scraping; a single failed request must not
    lose the whole run, and a failed chunk must not lose the other chunks.
    """
    failed = 0
    for i in range(0, len(rows), _INSERT_CHUNK):
        chunk = rows[i:i + _INSERT_CHUNK]
        for attempt in range(1, _INSERT_RETRIES + 1):
            try:
                get_client().table("priser").insert(chunk).execute()
                break
            except Exception as e:
                if attempt == _INSERT_RETRIES:
                    failed += len(chunk)
                    print(f"  [db] insert chunk failed after {attempt} attempts: {e}")
                else:
                    time.sleep(2 ** attempt)
    if failed:
        raise RuntimeError(f"{failed}/{len(rows)} price rows could not be inserted")

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
