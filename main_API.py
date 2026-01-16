# main_API.py
import requests
import json
import psycopg
import sqlite3
import os
from datetime import datetime
from twilio.rest import Client

# ======================
# 設定
# ======================
API_LIST = {
    "earthquake": "https://www.jma.go.jp/bosai/quake/data/list.json",
    "tsunami":    "https://www.jma.go.jp/bosai/tsunami/data/list.json",
}

# 環境変数
TEST_MODE = os.environ.get("TEST_MODE", "0") == "1"

DATABASE_URL = os.environ.get("DATABASE_URL")
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_FROM_PHONE = os.environ.get("TWILIO_FROM_PHONE")

client = (
    Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    if not TEST_MODE and TWILIO_ACCOUNT_SID
    else None
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SMS_DB_PATH = os.path.join(BASE_DIR, "sms_log.db")

# ======================
# DB接続
# ======================
def get_conn():
    return psycopg.connect(DATABASE_URL)

# ======================
# テスト用地震データ
# ======================
def get_test_earthquake_data():
    return {
        "eid": "TEST-20260116-001",
        "anm": "愛知県南部",
        "mag": "3.6",
        "maxi": "5",
        "at": "2026-01-16T13:39:58.727991"
    }

# ======================
# PostgreSQL 保存
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
# SQLite：最終イベントID
# ======================
def get_last_event_id(dtype):
    conn = sqlite3.connect("disaster.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS last_event (
            type TEXT PRIMARY KEY,
            event_id TEXT
        )
    """)
    cur.execute("SELECT event_id FROM last_event WHERE type=?", (dtype,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def update_last_event_id(data_type, event_id):
    conn = sqlite3.connect("disaster.db")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS last_event (
            type TEXT PRIMARY KEY,
            event_id TEXT
        )
    """)

    cur.execute("""
        INSERT INTO last_event(type, event_id)
        VALUES (?, ?)
        ON CONFLICT(type)
        DO UPDATE SET event_id=excluded.event_id
    """, (data_type, event_id))

    conn.commit()
    conn.close()

# ======================
# SMSログ保存
# ======================
def save_sms_log(phone, message, status):
    conn = sqlite3.connect(SMS_DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sms_log(
            user_phone TEXT,
            message TEXT,
            status TEXT,
            sent_at TEXT
        )
    """)
    cur.execute("""
        INSERT INTO sms_log VALUES (?, ?, ?, ?)
    """, (phone, message, status, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# ======================
# 通知（地震・津波）
# ======================
def send_disaster_sms(raw_json, dtype):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT phone, location FROM dis_users")
    users = cur.fetchall()
    cur.close()
    conn.close()

    if dtype == "earthquake":
        area = raw_json.get("anm", "")
        maxi = raw_json.get("maxi")

        try:
            maxi = int(maxi)
        except Exception:
            return

        if maxi < 4:
            return

        msg = f"[地震] {area} 最大震度 {maxi}"

    elif dtype == "tsunami":
        kind_list = raw_json.get("kind", [])
        if not kind_list:
            return

        kind_text = kind_list[0].get("kind", "")
        if "津波警報" not in kind_text and "大津波警報" not in kind_text:
            return

        area = raw_json.get("anm", "")
        msg = f"[津波] {area} {kind_text}"

    else:
        return

    for phone, location in users:
        if location not in area:
            continue

        if TEST_MODE:
            save_sms_log(phone, msg, "test")
            print(f"[TEST] {msg} -> {phone}")
        else:
            try:
                client.messages.create(
                    body=msg,
                    from_=TWILIO_FROM_PHONE,
                    to=phone
                )
                save_sms_log(phone, msg, "sent")
            except Exception as e:
                save_sms_log(phone, msg, "failed")
                print("[SMS ERROR]", e)

# ======================
# 災害処理
# ======================
def process_disaster(dtype, url):

    # ===== テストモード =====
    if TEST_MODE and dtype == "earthquake":
        latest = get_test_earthquake_data()
        event_id = latest["eid"]

        save_data("dis_quake_history", latest, "eid")
        update_last_event_id(dtype, event_id)

        print("[TEST MODE] 地震テストデータを保存しました")
        return

    # ===== 本番モード =====
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    data = res.json()
    if not data:
        return

    latest = data[0]
    event_id = latest.get("eid") or latest.get("tid")
    last_event_id = get_last_event_id(dtype)

    if event_id == last_event_id:
        return

    table = "dis_quake_history" if dtype == "earthquake" else "dis_tsunami_history"
    save_data(table, latest, "eid")
    send_disaster_sms(latest, dtype)
    update_last_event_id(dtype, event_id)

# ======================
# メイン
# ======================
if __name__ == "__main__":
    for dtype, url in API_LIST.items():
        process_disaster(dtype, url)

    print("Fetch & Notify finished")
