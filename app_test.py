# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
import psycopg
import hashlib
import json

app = Flask(__name__)
app.secret_key = "secret_key"

DB_CONFIG = {
    "dbname": "svnw",
    "user": "admin",
    "password": "admin",
    "host": "YOUR_DB_HOST",
    "port": "5432"
}

def get_conn():
    return psycopg.connect(**DB_CONFIG)

def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

# ======================
# ユーザー登録
# ======================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        location = request.form["location"]

        if not all([username, email, password, location]):
            flash("全ての項目を入力してください")
            return redirect(url_for("register"))

        hashed_pw = hash_password(password)

        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO dis_users (name, email, password, location)
                VALUES (%s, %s, %s, %s)
            """, (username, email, hashed_pw, location))
            conn.commit()
            cur.close()
            conn.close()
            flash("登録が完了しました")
            return redirect(url_for("login"))
        except psycopg.IntegrityError:
            flash("このメールアドレスは既に登録されています")
            return redirect(url_for("register"))

    # 47都道府県リスト
    prefectures = ["北海道","青森県","岩手県","宮城県","秋田県","山形県","福島県",
                   "茨城県","栃木県","群馬県","埼玉県","千葉県","東京都","神奈川県",
                   "新潟県","富山県","石川県","福井県","山梨県","長野県","岐阜県","静岡県",
                   "愛知県","三重県","滋賀県","京都府","大阪府","兵庫県","奈良県","和歌山県",
                   "鳥取県","島根県","岡山県","広島県","山口県","徳島県","香川県","愛媛県",
                   "高知県","福岡県","佐賀県","長崎県","熊本県","大分県","宮崎県","鹿児島県","沖縄県"]

    return render_template("register.html", prefectures=prefectures)

# ======================
# ログイン
# ======================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        hashed_pw = hash_password(password)

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM dis_users WHERE email=%s AND password=%s", (email, hashed_pw))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
            session["user_id"] = user[0]
            session["username"] = user[1]
            return redirect(url_for("dashboard"))
        else:
            flash("メールアドレスかパスワードが間違っています")
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
    # 最新10件の地震情報
    cur.execute("SELECT raw_json FROM dis_quake_history ORDER BY created_at DESC LIMIT 10")
    earthquakes = [json.loads(r[0]) for r in cur.fetchall()]
    # 最新10件の津波情報
    cur.execute("SELECT raw_json FROM dis_tsunami_history ORDER BY created_at DESC LIMIT 10")
    tsunamis = [json.loads(r[0]) for r in cur.fetchall()]
    # 最新10件の火山情報
    cur.execute("SELECT raw_json FROM dis_volcano_history ORDER BY created_at DESC LIMIT 10")
    volcanos = [json.loads(r[0]) for r in cur.fetchall()]
    cur.close()
    conn.close()

    return render_template("dashboard.html", earthquakes=earthquakes, tsunamis=tsunamis, volcanos=volcanos)

# ======================
# ログアウト
# ======================
@app.route("/logout")
def logout():
    session.clear()
    flash("ログアウトしました")
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
