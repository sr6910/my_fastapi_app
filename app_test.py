# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
import psycopg
import psycopg.errors
import hashlib
import json
import os

# ======================
# Flask 初期化
# ======================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")


# ======================
# DB 接続
# ======================
def get_conn():
    """
    Render / Cloud 用
    DATABASE_URL を必ず使う
    """
    return psycopg.connect(os.environ["DATABASE_URL"])


# ======================
# パスワードハッシュ
# ======================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# ======================
# トップページ
# ======================
@app.route("/")
def index():
    return redirect(url_for("login"))


# ======================
# ユーザー登録
# ======================
@app.route("/register", methods=["GET", "POST"])
def register():
    prefectures = [
        "北海道","青森県","岩手県","宮城県","秋田県","山形県","福島県",
        "茨城県","栃木県","群馬県","埼玉県","千葉県","東京都","神奈川県",
        "新潟県","富山県","石川県","福井県","山梨県","長野県","岐阜県","静岡県",
        "愛知県","三重県","滋賀県","京都府","大阪府","兵庫県","奈良県","和歌山県",
        "鳥取県","島根県","岡山県","広島県","山口県","徳島県","香川県","愛媛県",
        "高知県","福岡県","佐賀県","長崎県","熊本県","大分県","宮崎県","鹿児島県","沖縄県"
    ]

    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        location = request.form.get("location")

        if not all([username, email, password, location]):
            flash("全ての項目を入力してください")
            return redirect(url_for("register"))

        hashed_pw = hash_password(password)

        conn = None
        cur = None
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO dis_users (name, email, password, location)
                VALUES (%s, %s, %s, %s)
                """,
                (username, email, hashed_pw, location)
            )
            conn.commit()
            flash("登録が完了しました。ログインしてください。")
            return redirect(url_for("login"))

        except psycopg.errors.UniqueViolation:
            flash("このメールアドレスは既に登録されています")
            return redirect(url_for("register"))

        except Exception as e:
            flash("登録中にエラーが発生しました")
            print("[REGISTER ERROR]", e)
            return redirect(url_for("register"))

        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    return render_template("register.html", prefectures=prefectures)


# ======================
# ログイン
# ======================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        hashed_pw = hash_password(password)

        conn = None
        cur = None
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, name
                FROM dis_users
                WHERE email = %s AND password = %s
                """,
                (email, hashed_pw)
            )
            user = cur.fetchone()

        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

        if user:
            session["user_id"] = user[0]
            session["username"] = user[1]
            return redirect(url_for("dashboard"))
        else:
            flash("メールアドレスまたはパスワードが違います")
            return redirect(url_for("login"))

    return render_template("login.html")


# ======================
# ダッシュボード
# ======================
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        # 地震
        cur.execute(
            "SELECT raw_json FROM dis_quake_history ORDER BY created_at DESC LIMIT 10"
        )
        earthquakes = [json.loads(r[0]) for r in cur.fetchall()]

        # 津波
        cur.execute(
            "SELECT raw_json FROM dis_tsunami_history ORDER BY created_at DESC LIMIT 10"
        )
        tsunamis = [json.loads(r[0]) for r in cur.fetchall()]

        # 火山
        cur.execute(
            "SELECT raw_json FROM dis_volcano_history ORDER BY created_at DESC LIMIT 10"
        )
        volcanos = [json.loads(r[0]) for r in cur.fetchall()]

    except Exception as e:
        print("[DASHBOARD ERROR]", e)
        earthquakes, tsunamis, volcanos = [], [], []

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    return render_template(
        "dashboard.html",
        earthquakes=earthquakes,
        tsunamis=tsunamis,
        volcanos=volcanos
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
# Render / 本番起動
# ======================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
