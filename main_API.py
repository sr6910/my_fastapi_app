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

# ======================
# テストモード
# ======================
TEST_MODE = os.environ.get("TEST_MODE", "0") == "1"

# ======================
# Twilio
# ======================
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_FROM_PHONE = os.environ.get("TWILIO_FROM_PHONE")
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID else None

# ======================
# ログ用 SQLite
# ======================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SMS_DB_PATH = os.path.join(BASE_DIR, "sms_log.db")

# ======================
# PostgreSQL接続
# ======================
def get_conn():
    return psycopg.connect(os.environ["DATABASE_URL"])

# ======================
# PostgreSQLにraw_jsonを保存
# ======================
def save_data(table, raw_json, eid_key="eid"):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"""
        INSERT INTO {table} (eid, raw_json, created_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (eid) DO NOTHING
    """, (
        raw_json.get(eid_key),
        json.dumps(raw_json, ensure_ascii=False)
    ))
    conn.commit()
    cur.close()
    conn.close()

# ======================
# SQLite：最後に取得した event_id（本番のみ）
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
# SMSログ保存
# ======================
def save_sms_log(user_phone, message, status, twilio_sid=None):
    conn = sqlite3.connect(SMS_DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sms_log(
            user_phone TEXT,
            message TEXT,
            status TEXT,
            twilio_sid TEXT,
            sent_at TEXT
        )
    """)
    cur.execute("""
        INSERT INTO sms_log
        (user_phone, message, status, twilio_sid, sent_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        user_phone,
        message,
        status,
        twilio_sid,
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()

# ======================
#日本の携帯番号を Twilio 用 (E.164) に変換
# ======================

def normalize_phone_jp(phone: str) -> str:
    phone = phone.replace("-", "").strip()

    if phone.startswith("+"):
        return phone  # すでに国番号付き

    if phone.startswith("0"):
        return "+81" + phone[1:]

    return phone  # 想定外はそのまま


# ======================
# 通知送信（県別・条件判定）
# ======================
def send_disaster_sms(raw_json, dtype):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT phone, location FROM dis_users")
    users = cur.fetchall()
    cur.close()
    conn.close()

    if dtype == "earthquake":
        quake_area = raw_json.get("anm", "")
        maxi = raw_json.get("maxi")
        if not maxi:
            return

        try:
            maxi_val = int(maxi)
        except ValueError:
            return

        if maxi_val < 4:
            return

        # 地震メッセージ作成
        msg = f"[地震] {quake_area} 最大震度 {maxi_val}\n水（1人1日3L × 3日以上）\n非常食（3日分以上）\nを持って逃げましょう。"


    else:  # tsunami
        kind_list = raw_json.get("kind")
        if not kind_list:
            return

        kind_text = kind_list[0].get("kind", "")
        if "津波警報" not in kind_text and "大津波警報" not in kind_text:
            return

        # 津波メッセージ作成
        msg = f"[津波] {raw_json.get('anm')} {kind_text}\n水（1人1日3L × 3日以上）\n非常食（3日分以上）\nを持って逃げましょう。"

    for phone, location in users:
        if location not in raw_json.get("anm", ""):
            continue

        phone_e164 = normalize_phone_jp(phone)

    try:
        message = client.messages.create(
            body=msg,
            from_=TWILIO_FROM_PHONE,
            to=phone_e164
        )
        save_sms_log(phone_e164, msg, status="sent", twilio_sid=message.sid)    

    except Exception as e:
        save_sms_log(phone, msg, status="failed")
        print("Twilio error:", e)


# ======================
# 災害データ処理
# ======================
def process_disaster(data_type, url):
    # ---------- テストモード ----------
    if TEST_MODE:
        now = datetime.now().strftime("%Y%m%d%H%M%S")

        if data_type == "earthquake":
            raw_json = {
                "eid": f"TEST-EQ-{now}",
                "anm": "愛知県南部",
                "mag": "4.1",
                "maxi": "7",
                "at": datetime.now().isoformat()
            }
            save_data("dis_quake_history", raw_json)
            send_disaster_sms(raw_json, "earthquake")

        """
        elif data_type == "tsunami":
            raw_json = {
                "eid": f"TEST-TS-{now}",
                "anm": "青森県東方沖",
                "kind": [{"kind": "津波注意報"}],
                "at": datetime.now().isoformat()
            }
            save_data("dis_tsunami_history", raw_json)
            send_disaster_sms(raw_json, "tsunami")
        """

        print(f"[TEST MODE] earthquake/tsunami sent via Twilio")
        return

    # ---------- 本番モード ----------
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    data = res.json()
    if not data:
        return

    latest = data[0]
    event_id = latest.get("eid") or latest.get("tid")
    last_event_id = get_last_event_id(data_type)

    if event_id != last_event_id:
        table = "dis_quake_history" if data_type == "earthquake" else "dis_tsunami_history"
        save_data(table, latest)
        send_disaster_sms(latest, data_type)
        update_last_event_id(data_type, event_id)

# ======================
# メイン処理
# ======================
if __name__ == "__main__":
    for dtype, url in API_LIST.items():
        process_disaster(dtype, url)

    print("Fetch & Notify finished")
