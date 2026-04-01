import os
import logging
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]
        _client = create_client(url, key)
    return _client


def get_api_key(service_name: str) -> str:
    """api_keys 테이블에서 키 값을 조회한다. (컬럼: service, api_key)"""
    client = get_client()
    resp = client.table("api_keys").select("api_key").eq("service", service_name).single().execute()
    return resp.data["api_key"]


def get_unused_item(table: str, filter_col: str | None = None, filter_val: str | None = None) -> dict | None:
    """is_used=false인 항목 1개를 반환한다. 추가 필터 조건을 줄 수 있다."""
    client = get_client()
    query = client.table(table).select("*").eq("is_used", False)
    if filter_col and filter_val:
        query = query.eq(filter_col, filter_val)
    resp = query.limit(1).execute()
    if resp.data:
        return resp.data[0]
    return None


def mark_as_used(table: str, item_id: int) -> None:
    """항목의 is_used를 true로 업데이트한다."""
    client = get_client()
    client.table(table).update({"is_used": True}).eq("id", item_id).execute()
    logger.info(f"[{table}] id={item_id} marked as used")


def get_next_category(table: str = "history_categories") -> dict | None:
    """last_used_at 기준 가장 오래된 카테고리를 반환한다."""
    client = get_client()
    resp = (
        client.table(table)
        .select("*")
        .order("last_used_at", desc=False)
        .limit(1)
        .execute()
    )
    if resp.data:
        return resp.data[0]
    return None


def reset_used_items(table: str, filter_col: str | None = None, filter_val: str | None = None) -> int:
    """is_used=true인 항목을 전부 false로 리셋한다. 리셋된 건수를 반환한다."""
    client = get_client()
    query = client.table(table).update({"is_used": False}).eq("is_used", True)
    if filter_col and filter_val:
        query = query.eq(filter_col, filter_val)
    resp = query.execute()
    count = len(resp.data) if resp.data else 0
    logger.info(f"[{table}] is_used 리셋 완료: {count}건")
    return count


def get_next_week(channel: str) -> dict | None:
    """weekly_schedule 테이블에서 다음 미사용 주차를 반환한다."""
    return get_unused_item("weekly_schedule", "channel", channel)


def mark_week_used(week_id: int) -> None:
    """주차의 is_used를 true로 업데이트한다."""
    mark_as_used("weekly_schedule", week_id)


def update_category_used(table: str, item_id: int) -> None:
    """카테고리의 last_used_at을 현재 시각으로 업데이트한다."""
    from datetime import datetime, timezone
    client = get_client()
    client.table(table).update({
        "last_used_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", item_id).execute()
