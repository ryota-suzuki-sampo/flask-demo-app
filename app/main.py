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
    charter_type = request.form["charter_type"]
    flag = request.form["flag"]
    ship_type = request.form["ship_type"]
    completion_date = request.form["completion_date"]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ships (ship_name, company_name, charter_type, flag, ship_type, completion_date)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (ship_name, company_name, charter_type, flag, ship_type, completion_date))
    return redirect("/ships")

@app.route("/ships")
def list_ships():
    search = request.args.get("search", "")
    sort = request.args.get("sort", "id")  # デフォルトはid
    order = request.args.get("order", "desc")  # デフォルトは降順

    # SQLインジェクション防止：許可された列・順だけ使う
    allowed_sorts = ["id", "ship_name", "company_name", "completion_date"]
    allowed_orders = ["asc", "desc"]
    sort = sort if sort in allowed_sorts else "id"
    order = order if order in allowed_orders else "desc"

    with get_conn() as conn:
        with conn.cursor() as cur:
            if search:
                cur.execute(f"""
                    SELECT id, ship_name, company_name, charter_type, completion_date, flag, ship_type
                    FROM ships
                    WHERE ship_name ILIKE %s OR company_name ILIKE %s
                    ORDER BY {sort} {order}
                """, (f"%{search}%", f"%{search}%"))
            else:
                cur.execute(f"""
                    SELECT id, ship_name, company_name, charter_type, completion_date, flag, ship_type
                    FROM ships
                    ORDER BY {sort} {order}
                """)
            ships = cur.fetchall()
    return render_template("ships.html", ships=ships, search=search, sort=sort, order=order)


if __name__ == "__main__":
    print("Starting app on port 5000...")
    app.run(host="0.0.0.0", port=5000)
