# main_API.py
import requests
import json
import psycopg
import sqlite3
import os
from datetime import datetime

# ======================
# テストモード
# ======================
TEST_MODE = os.environ.get("TEST_MODE", "0") == "1"

# ======================
# 気象庁 API
# ======================
API_LIST = {
    "earthquake": "https://www.jma.go.jp/bosai/quake/data/list.json",
    "tsunami":    "https://www.jma.go.jp/bosai/tsunami/data/list.json",
}

# ======================
# PostgreSQL 接続
# ======================
def get_conn():
    return psycopg.connect(os.environ["DATABASE_URL"])

# ======================
# DB 保存（raw_json に丸ごと保存）
# ======================
def save_data(table, raw_json):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"""
        INSERT INTO {table} (eid, raw_json, created_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (eid) DO NOTHING
    """, (
        raw_json["eid"],
        json.dumps(raw_json, ensure_ascii=False)
    ))
    conn.commit()
    cur.close()
    conn.close()

# ======================
# SQLite: last_event 管理（本番のみ）
# ======================
def get_last_event_id(data_type):
    conn = sqlite3.connect("disaster.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS last_event (
            type TEXT PRIMARY KEY,
            event_id TEXT
        )
    """)
    cur.execute(
        "SELECT event_id FROM last_event WHERE type=?",
        (data_type,)
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def update_last_event_id(data_type, event_id):
    conn = sqlite3.connect("disaster.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO last_event(type, event_id)
        VALUES (?, ?)
        ON CONFLICT(type)
        DO UPDATE SET event_id=excluded.event_id
    """, (data_type, event_id))
    conn.commit()
    conn.close()

# ======================
# 災害データ処理
# ======================
def process_disaster(data_type, url):
    # -------- テストモード --------
    if TEST_MODE:
        now = datetime.now().strftime("%Y%m%d%H%M%S")

        if data_type == "earthquake":
            raw_json = {
                "eid": f"TEST-EQ-{now}",
                "anm": "テスト地域",
                "mag": "5.6",
                "maxi": "3",
                "at": "2026-01-01T12:00:00+09:00"
            }
            save_data("dis_quake_history", raw_json)

        elif data_type == "tsunami":
            raw_json = {
                "eid": f"TEST-TS-{now}",
                "anm": "テスト沿岸",
                "kind": [
                    {
                        "code": "900",
                        "kind": "津波注意報"
                    }
                ],
                "at": "2026-01-01T12:00:00+09:00"
            }
            save_data("dis_tsunami_history", raw_json)

        print(f"[TEST MODE] inserted {data_type}")
        return

    # -------- 本番モード --------
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    data = res.json()
    if not data:
        return

    latest = data[0]
    event_id = latest.get("eid") or latest.get("tid")
    last_event_id = get_last_event_id(data_type)

    if event_id != last_event_id:
        if data_type == "earthquake":
            save_data("dis_quake_history", latest)
        elif data_type == "tsunami":
            save_data("dis_tsunami_history", latest)

        update_last_event_id(data_type, event_id)

# ======================
# メイン
# ======================
if __name__ == "__main__":
    for dtype, url in API_LIST.items():
        process_disaster(dtype, url)

    print("Fetch finished")
