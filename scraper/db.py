import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
_client = None

def get_client():
    global _client
    if _client is None:
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"]
        )
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
