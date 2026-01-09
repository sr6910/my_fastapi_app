# main_API.py（地震＋津波 県別・震度／警報判定対応完全版）
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

# Twilio
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_FROM_PHONE = os.environ.get("TWILIO_FROM_PHONE")
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID else None

# テストモード
TEST_MODE = os.environ.get("TEST_MODE", "0") == "1"

# ログ用 SQLite
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
# 通知送信（県別・条件判定）
# ======================
def send_disaster_sms(raw_json, dtype):
    conn = get_conn()
    cur = conn.cursor()
    # ユーザー情報を取得（電話番号と都道府県）
    cur.execute("SELECT phone, location FROM dis_users")
    users = cur.fetchall()
    cur.close()
    conn.close()

    if dtype == "earthquake":
        quake_area = raw_json.get('anm')
        maxi = raw_json.get('maxi')
        if not maxi:
            return
        try:
            maxi_val = int(maxi)
        except ValueError:
            return

        if maxi_val < 4:  # 震度4未満は通知しない
            return

        msg = f"[地震] {quake_area} 最大震度 {maxi_val}"

        for phone, location in users:
            if location not in quake_area:
                continue
            if TEST_MODE:
                save_sms_log(phone, msg, status='test')
                print(f"[TEST MODE] SMSログ作成: {msg} -> {phone}")
            else:
                try:
                    message = client.messages.create(
                        body=msg,
                        from_=TWILIO_FROM_PHONE,
                        to=phone
                    )
                    save_sms_log(phone, msg, status='sent', twilio_sid=message.sid)
                    print(f"SMS送信成功: {msg} -> {phone}")
                except Exception as e:
                    save_sms_log(phone, msg, status='failed')
                    print(f"SMS送信失敗: {msg} -> {phone}, error={e}")

    elif dtype == "tsunami":
        # 津波の場合は警報種別をチェック
        kind_list = raw_json.get('kind')
        if not kind_list:
            return
        kind_text = kind_list[0].get('kind', '不明')
        # 「津波注意報」は無視、「津波警報」以上のみ通知
        if "津波警報" not in kind_text and "大津波警報" not in kind_text:
            return

        msg = f"[津波] {raw_json.get('anm')} {kind_text}"

        for phone, location in users:
            # ユーザーの都道府県が津波対象地域に含まれていれば通知
            tsunami_area = raw_json.get('anm', '')
            if location not in tsunami_area:
                continue

            if TEST_MODE:
                save_sms_log(phone, msg, status='test')
                print(f"[TEST MODE] SMSログ作成: {msg} -> {phone}")
            else:
                try:
                    message = client.messages.create(
                        body=msg,
                        from_=TWILIO_FROM_PHONE,
                        to=phone
                    )
                    save_sms_log(phone, msg, status='sent', twilio_sid=message.sid)
                    print(f"SMS送信成功: {msg} -> {phone}")
                except Exception as e:
                    save_sms_log(phone, msg, status='failed')
                    print(f"SMS送信失敗: {msg} -> {phone}, error={e}")

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
        table = "dis_quake_history" if data_type=="earthquake" else "dis_tsunami_history"
        save_data(table, latest, "eid")  # raw_json に保存
        send_disaster_sms(latest, data_type)  # 通知
        update_last_event_id(data_type, event_id)  # 最終更新

# ======================
# メイン処理
# ======================
if __name__ == "__main__":
    for dtype, url in API_LIST.items():
        process_disaster(dtype, url)
    print("Fetch & Notify finished (earthquake & tsunami)")
