# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
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
    # Render の Environment に設定した DATABASE_URL を使う
    return psycopg.connect(os.environ["DATABASE_URL"])

# ======================
# パスワードハッシュ
# ======================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# ======================
# トップ（ログインへ）
# ======================
@app.route("/")
def index():
    return redirect(url_for("login"))

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

        # 入力チェック
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

        # 重複（電話番号）
        except psycopg.errors.UniqueViolation:
            flash("この電話番号は既に登録されています")
            return redirect(url_for("register"))

        # DB 接続系エラー
        except psycopg.OperationalError:
            flash("現在データベースに接続できません。時間をおいて再度お試しください。")
            return redirect(url_for("register"))

        # その他すべて
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

    # 47都道府県
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
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_conn()
    cur = conn.cursor()

    # 地震
    cur.execute("""
        SELECT raw_json
        FROM dis_quake_history
        ORDER BY created_at DESC
        LIMIT 10
    """)
    earthquakes = [json.loads(r[0]) for r in cur.fetchall()]

    # 津波
    cur.execute("""
        SELECT raw_json
        FROM dis_tsunami_history
        ORDER BY created_at DESC
        LIMIT 10
    """)
    tsunamis = [json.loads(r[0]) for r in cur.fetchall()]

    cur.close()
    conn.close()

    return render_template(
        "dashboard.html",
        earthquakes=earthquakes,
        tsunamis=tsunamis
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
    # Render では gunicorn が使うので通常ここは使われない
    app.run(host="0.0.0.0", port=8080, debug=True)
