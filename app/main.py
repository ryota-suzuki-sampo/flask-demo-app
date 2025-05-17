from flask import Flask, render_template, request, redirect
import os
import psycopg2

app = Flask(__name__, template_folder="templates")

# DB接続
def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

# トップ（登録フォーム）
@app.route("/")
def index():
    return render_template("index.html")

# 登録処理
@app.route("/submit", methods=["POST"])
def submit():
    ship_name = request.form["ship_name"]
    company_name = request.form["company_name"]
    charter_type = request.form["charter_type"]
    flag = request.form["flag"]
    ship_type = request.form["ship_type"]
    completion_date = request.form["completion_date"]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ships (
                    ship_name, company_name, charter_type, flag, ship_type, completion_date
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                ship_name, company_name, charter_type, flag, ship_type, completion_date
            ))
    return redirect("/ships")

# 一覧表示
@app.route("/ships")
def list_ships():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, ship_name, company_name, charter_type, completion_date, flag, ship_type
                FROM ships ORDER BY id DESC
            """)
            ships = cur.fetchall()
    return render_template("ships.html", ships=ships)

# Railwayでは固定ポートが必要
if __name__ == "__main__":
    print("Starting app on port 5000...")
    app.run(host="0.0.0.0", port=5000)
