"""
Supabase weekly_schedule 테이블 초기화 스크립트

사용법:
    python3 scripts/setup_weekly_schedule.py           # 소스 폴더 있는 주차만 등록
    python3 scripts/setup_weekly_schedule.py --all     # CSV 전체 52주 등록 (폴더 없어도)
    python3 scripts/setup_weekly_schedule.py --list    # 현재 등록 목록 조회

Supabase SQL (최초 1회 실행):
    CREATE TABLE IF NOT EXISTS weekly_schedule (
        id        SERIAL PRIMARY KEY,
        channel   TEXT    NOT NULL,
        week_num  INTEGER NOT NULL,
        folder_name TEXT  NOT NULL,
        title_kr  TEXT,
        is_used   BOOLEAN DEFAULT FALSE,
        UNIQUE(channel, week_num)
    );
"""

import os
import sys
import csv
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from shared.supabase_client import get_client

BASE_DIR     = Path(__file__).resolve().parent.parent
SOURCE2_DIR  = BASE_DIR / "channel2_source"
SOURCE3_DIR  = BASE_DIR / "channel3_source"
CSV2         = SOURCE2_DIR / "52weeks_dinosaurs.csv"
CSV3         = SOURCE3_DIR / "52weeks_history.csv"


def folder_name(channel: str, week_num: int) -> str:
    """소스 폴더명 규칙: w01_dino_source / w01_his_source"""
    suffix = "dino_source" if channel == "dino" else "his_source"
    return f"w{week_num:02d}_{suffix}"


def source_dir(channel: str) -> Path:
    return SOURCE2_DIR if channel == "dino" else SOURCE3_DIR


def load_csv(channel: str) -> list[dict]:
    """CSV 파일에서 주차 목록을 읽는다."""
    csv_path = CSV2 if channel == "dino" else CSV3
    rows = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            week_num = int(row["week"])
            rows.append({
                "channel":     channel,
                "week_num":    week_num,
                "folder_name": folder_name(channel, week_num),
                "title_kr":    row["title_kr"],
                "is_used":     False,
            })
    return rows


def register(channel: str, only_existing: bool = True) -> int:
    """weekly_schedule 테이블에 주차 데이터를 삽입한다. 삽입 건수 반환."""
    rows = load_csv(channel)
    client = get_client()
    inserted = 0

    for row in rows:
        folder_path = source_dir(channel) / row["folder_name"]
        if only_existing and not folder_path.is_dir():
            print(f"  [SKIP] {row['folder_name']} — 폴더 없음")
            continue

        # UPSERT (중복 week_num 시 무시)
        resp = (
            client.table("weekly_schedule")
            .upsert(row, on_conflict="channel,week_num", ignore_duplicates=True)
            .execute()
        )
        status = "OK" if resp.data is not None else "?"
        print(f"  [{status}] {row['channel']} w{row['week_num']:02d} — {row['title_kr']}")
        inserted += 1

    return inserted


def list_schedule() -> None:
    """현재 등록된 weekly_schedule 목록을 출력한다."""
    client = get_client()
    resp = (
        client.table("weekly_schedule")
        .select("channel,week_num,folder_name,title_kr,is_used")
        .order("channel")
        .order("week_num")
        .execute()
    )
    if not resp.data:
        print("(등록된 데이터 없음)")
        return

    current_channel = None
    for row in resp.data:
        if row["channel"] != current_channel:
            current_channel = row["channel"]
            print(f"\n=== {current_channel.upper()} ===")
        used = "✓" if row["is_used"] else "○"
        print(f"  {used} w{row['week_num']:02d} {row['title_kr']}")


def main():
    parser = argparse.ArgumentParser(description="Supabase weekly_schedule 초기화")
    parser.add_argument("--all",  action="store_true", help="폴더 없어도 CSV 전체 등록")
    parser.add_argument("--list", action="store_true", help="현재 등록 목록 조회")
    args = parser.parse_args()

    if args.list:
        list_schedule()
        return

    only_existing = not args.all

    print("=== 채널2 (dino) 등록 ===")
    n2 = register("dino", only_existing=only_existing)

    print("\n=== 채널3 (history) 등록 ===")
    n3 = register("history", only_existing=only_existing)

    print(f"\n완료: dino {n2}건, history {n3}건 등록")


if __name__ == "__main__":
    main()
