# app.py
from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, session, g
)
import psycopg
import hashlib
import json
import os

# ======================
# Flask 基本設定
# ======================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")

# ======================
# DB 接続（Render 用）
# ======================
def get_conn():
    return psycopg.connect(os.environ["DATABASE_URL"])

# ======================
# パスワードハッシュ
# ======================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# ======================
# ログ用ユーティリティ
# ======================
def safe_params():
    params = request.values.to_dict()
    params.pop("password", None)  # パスワード除外
    return params

def infer_action():
    if request.path == "/login" and request.method == "POST":
        return "login"
    if request.path == "/logout":
        return "logout"
    if request.path == "/register" and request.method == "POST":
        return "register"
    if request.path == "/dashboard":
        return "view_dashboard"
    return "access"

# ======================
# ログ開始（全リクエスト）
# ======================
@app.before_request
def before_request():
    g.log_data = {
        "user_id": session.get("user_id"),
        "method": request.method,
        "path": request.path,
        "params": safe_params(),
        "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
        "user_agent": request.user_agent.string
    }

# ======================
# ログ保存（全レスポンス）
# ======================
@app.after_request
def after_request(response):
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO user_action_logs
            (user_id, action, method, path, params, ip, user_agent, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            g.log_data.get("user_id"),
            infer_action(),
            g.log_data.get("method"),
            g.log_data.get("path"),
            json.dumps(g.log_data.get("params")),
            g.log_data.get("ip"),
            g.log_data.get("user_agent"),
            response.status_code
        ))

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print("[ACTION LOG ERROR]", e)

    return response

# ======================
# 防災物資定義
# ======================
SUPPLIES = {
    "common": [
        "水（1人1日3L × 3日以上）",
        "非常食（3日分以上）",
        "懐中電灯・予備電池",
        "モバイルバッテリー",
        "現金",
        "ヘルメット／防災頭巾",
        "笛（ホイッスル）"
    ],
    "baby": [
        "ミルク（液体タイプ推奨）",
        "哺乳瓶",
        "離乳食",
        "紙おむつ",
        "おしりふき",
        "着替え（多め）"
    ],
    "pet": [
        "ペットフード",
        "ペット用の水",
        "ペットシーツ",
        "リード",
        "ワクチン証明書のコピー"
    ],
    "medical": [
        "常備薬（多め）",
        "お薬手帳",
        "医療機器・予備電源",
        "アレルギー対応薬"
    ],
    "elderly": [
        "老眼鏡",
        "補聴器・予備電池",
        "杖",
        "介護用品"
    ],
    "female": [
        "生理用品",
        "デリケートゾーンケア用品",
        "防犯対策グッズ"
    ],
    "alone": [
        "安否確認用連絡先リスト",
        "近隣避難所の地図"
    ],

    "pregnant": [
        "母子手帳",
        "マタニティ用品",
        "かかりつけ病院の連絡先"
    ],

    "allergy": [
        "アレルギー対応食品",
        "アレルギー表示カード"
    ],

    "home": [
        "簡易トイレ（多め）",
        "カセットコンロ・ガス"
    ],

    "car": [
        "車載非常用キット",
        "ガソリン携行缶",
        "ブランケット"
    ],

    "foreign": [
        "多言語防災ガイド",
        "翻訳アプリ（オフライン）"
    ]

}

# ======================
# トップページ
# ======================
@app.route("/")
def index():
    return redirect(url_for("dashboard"))

# ======================
# ユーザー登録
# ======================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        phone = request.form.get("phone")
        password = request.form.get("password")
        location = request.form.get("location")

        if not all([username, phone, password, location]):
            flash("全ての項目を入力してください")
            return redirect(url_for("register"))

        hashed_pw = hash_password(password)

        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO dis_users (name, phone, password, location)
                VALUES (%s, %s, %s, %s)
            """, (username, phone, hashed_pw, location))
            conn.commit()

        except psycopg.errors.UniqueViolation:
            flash("この電話番号は既に登録されています")
            return redirect(url_for("register"))

        except psycopg.OperationalError:
            flash("現在データベースに接続できません")
            return redirect(url_for("register"))

        except Exception as e:
            print("[REGISTER ERROR]", e)
            flash("登録中にエラーが発生しました")
            return redirect(url_for("register"))

        finally:
            if 'cur' in locals():
                cur.close()
            if 'conn' in locals():
                conn.close()

        flash("登録が完了しました")
        return redirect(url_for("login"))

    prefectures = [
        "北海道","青森県","岩手県","宮城県","秋田県","山形県","福島県",
        "茨城県","栃木県","群馬県","埼玉県","千葉県","東京都","神奈川県",
        "新潟県","富山県","石川県","福井県","山梨県","長野県","岐阜県","静岡県",
        "愛知県","三重県","滋賀県","京都府","大阪府","兵庫県","奈良県","和歌山県",
        "鳥取県","島根県","岡山県","広島県","山口県","徳島県","香川県","愛媛県",
        "高知県","福岡県","佐賀県","長崎県","熊本県","大分県","宮崎県","鹿児島県","沖縄県"
    ]

    return render_template("register.html", prefectures=prefectures)

# ======================
# ログイン
# ======================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone")
        password = request.form.get("password")

        if not phone or not password:
            flash("電話番号とパスワードを入力してください")
            return redirect(url_for("login"))

        hashed_pw = hash_password(password)

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name FROM dis_users
            WHERE phone = %s AND password = %s
        """, (phone, hashed_pw))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
            session["user_id"] = user[0]
            session["username"] = user[1]
            return redirect(url_for("dashboard"))
        else:
            flash("電話番号またはパスワードが間違っています")
            return redirect(url_for("login"))

    return render_template("login.html")

# ======================
# ダッシュボード
# ======================
@app.route("/dashboard")
def dashboard():

    conn = get_conn()
    cur = conn.cursor()

    # 地震
    cur.execute("""
        SELECT
            raw_json->>'anm',
            raw_json->>'mag',
            raw_json->>'maxi',
            created_at
        FROM dis_quake_history
        ORDER BY created_at DESC
        LIMIT 10
    """)
    earthquakes = cur.fetchall()

    # 津波
    cur.execute("""
        SELECT
            raw_json->>'anm',
            raw_json->'kind'->0->>'kind',
            CASE
                WHEN raw_json->'kind'->0->>'kind' LIKE '%大津波警報%' THEN 3
                WHEN raw_json->'kind'->0->>'kind' LIKE '%津波警報%' THEN 2
                WHEN raw_json->'kind'->0->>'kind' LIKE '%津波注意報%' THEN 1
                ELSE 0
            END,
            created_at
        FROM dis_tsunami_history
        ORDER BY created_at DESC
        LIMIT 10
    """)
    tsunamis = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "dashboard.html",
        earthquakes=earthquakes,
        tsunamis=tsunamis
    )

# ======================
# 自分の県の災害履歴
# ======================
@app.route("/dis_his")
def my_history():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_conn()
    cur = conn.cursor()

    # ユーザーの登録県
    cur.execute(
        "SELECT location FROM dis_users WHERE id = %s",
        (session["user_id"],)
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        flash("ユーザー情報が取得できません")
        return redirect(url_for("dashboard"))

    user_pref = row[0]

    # ----------------------
    # 地震履歴（県フィルタ）
    # ----------------------
    cur.execute("""
        SELECT
            raw_json->>'anm'  AS area,
            raw_json->>'mag'  AS mag,
            raw_json->>'maxi' AS maxi,
            created_at
        FROM dis_quake_history
        WHERE raw_json->>'anm' LIKE %s
        ORDER BY created_at DESC
        LIMIT 50
    """, (f"%{user_pref}%",))
    earthquakes = cur.fetchall()

    # ----------------------
    # 津波履歴（県フィルタ）
    # ----------------------
    cur.execute("""
        SELECT
            raw_json->>'anm' AS area,
            raw_json->'kind'->0->>'kind' AS kind,
            created_at
        FROM dis_tsunami_history
        WHERE raw_json->>'anm' LIKE %s
        ORDER BY created_at DESC
        LIMIT 50
    """, (f"%{user_pref}%",))
    tsunamis = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "dis_his.html",
        user_pref=user_pref,
        earthquakes=earthquakes,
        tsunamis=tsunamis
    )

# ====================== 
# 事前準備ページ 
# ======================
@app.route("/prepare")
def prepare():
    return render_template("prepare.html", logged_in="user_id" in session)

# ======================
# 専用準備ページ
# ======================
@app.route("/pre_check")
def pre_check():
    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "pre_check.html",
        logged_in=True
    )

# ======================
# 事前準備チェック結果
# ======================
@app.route("/pre_check/pre_result", methods=["POST"])
def prepare_result():
    # チェックされた条件を取得
    selected = {
        "elderly": request.form.get("elderly"),
        "baby": request.form.get("baby"),
        "pet": request.form.get("pet"),
        "medical": request.form.get("medical"),
        "female": request.form.get("female")
    }

    # 表示する物資をまとめる
    result = {
        "common": SUPPLIES["common"]
    }

    for key, value in selected.items():
        if value:
            result[key] = SUPPLIES.get(key, [])

    return render_template(
        "pre_result.html",
        supplies=result
    )

# ======================
# ログアウト
# ======================
@app.route("/logout")
def logout():
    session.clear()
    flash("ログアウトしました")
    return redirect(url_for("login"))

# ======================
# 起動
# ======================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
