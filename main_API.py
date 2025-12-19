# fetch_disaster.py
import requests
import json
import psycopg
import sqlite3
import os

# ======================
# 気象庁 API（地震・津波のみ）
# ======================
API_LIST = {
    "earthquake": "https://www.jma.go.jp/bosai/quake/data/list.json",
    "tsunami":    "https://www.jma.go.jp/bosai/tsunami/data/list.json",
}

# ======================
# PostgreSQL 接続（Render）
# ======================
def get_conn():
    return psycopg.connect(os.environ["DATABASE_URL"])

# ======================
# PostgreSQL に保存
# ======================
def save_data(table, latest, eid_key):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"""
        INSERT INTO {table} (eid, raw_json, created_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (eid) DO NOTHING;
    """, (
        latest.get(eid_key),
        json.dumps(latest, ensure_ascii=False)
    ))
    conn.commit()
    cur.close()
    conn.close()

# ======================
# SQLite：最後に取得した event_id を管理
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
# 災害データ取得処理
# ======================
def process_disaster(data_type, url):
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
            save_data("dis_quake_history", latest, "eid")
        elif data_type == "tsunami":
            save_data("dis_tsunami_history", latest, "eid")

        update_last_event_id(data_type, event_id)

# ======================
# メイン処理
# ======================
if __name__ == "__main__":
    for dtype, url in API_LIST.items():
        process_disaster(dtype, url)

    print("Fetch finished (earthquake & tsunami only)")
