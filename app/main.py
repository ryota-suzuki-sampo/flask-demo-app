from flask import Flask, render_template, request, redirect
import os
import psycopg2

app = Flask(__name__, template_folder="templates")

def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/submit", methods=["POST"])
def submit():
    ship_name = request.form["ship_name"]
    company_name = request.form["company_name"]
    completion_date = request.form["completion_date"]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ships (ship_name, company_name, completion_date)
                VALUES (%s, %s, %s)
            """, (ship_name, company_name, completion_date))
    return redirect("/ships")

@app.route("/ships")
def list_ships():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, ship_name, company_name, completion_date FROM ships ORDER BY id DESC")
            ships = cur.fetchall()
    return render_template("ships.html", ships=ships)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
