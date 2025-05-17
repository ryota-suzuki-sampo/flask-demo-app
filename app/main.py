from flask import Flask, render_template, request, redirect
import os
import psycopg2
from flask import Flask, render_template, request, redirect, url_for

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
    sort = request.args.get("sort", "id")
    order = request.args.get("order", "desc")
    page = int(request.args.get("page", 1))
    per_page = 10
    offset = (page - 1) * per_page

    allowed_sorts = ["id", "ship_name", "company_name", "completion_date"]
    allowed_orders = ["asc", "desc"]
    sort = sort if sort in allowed_sorts else "id"
    order = order if order in allowed_orders else "desc"

    with get_conn() as conn:
        with conn.cursor() as cur:
            if search:
                cur.execute("""
                    SELECT COUNT(*) FROM ships
                    WHERE ship_name ILIKE %s OR company_name ILIKE %s
                """, (f"%{search}%", f"%{search}%"))
            else:
                cur.execute("SELECT COUNT(*) FROM ships")
            total = cur.fetchone()[0]
            total_pages = (total + per_page - 1) // per_page

            if search:
                cur.execute(f"""
                    SELECT id, ship_name, company_name, charter_type, completion_date, flag, ship_type
                    FROM ships
                    WHERE ship_name ILIKE %s OR company_name ILIKE %s
                    ORDER BY {sort} {order}
                    LIMIT {per_page} OFFSET {offset}
                """, (f"%{search}%", f"%{search}%"))
            else:
                cur.execute(f"""
                    SELECT id, ship_name, company_name, charter_type, completion_date, flag, ship_type
                    FROM ships
                    ORDER BY {sort} {order}
                    LIMIT {per_page} OFFSET {offset}
                """)
            ships = cur.fetchall()

    return render_template("ships.html", ships=ships, search=search, sort=sort, order=order, page=page, total_pages=total_pages)

@app.route("/ships/<int:ship_id>")
def ship_detail(ship_id):
    edit_mode = request.args.get("edit") == "1"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ship_name FROM ships WHERE id = %s", (ship_id,))
            ship = cur.fetchone()
            if not ship:
                return "Not Found", 404

            cur.execute("SELECT id, name FROM currencies")
            currencies = cur.fetchall()

            cur.execute("""
                SELECT charter_currency_id, charter_fee,
                       ship_currency_id, ship_cost,
                       repayment_currency_id, repayment,
                       interest_currency_id, interest
                FROM ship_details WHERE ship_id = %s
            """, (ship_id,))
            detail = cur.fetchone()

    return render_template("ship_detail.html",
                           ship_id=ship_id,
                           ship_name=ship[0],
                           currencies=currencies,
                           detail=detail,
                           edit=edit_mode)


@app.route("/ships/<int:ship_id>/update", methods=["POST"])
def update_ship_detail(ship_id):
    data = {
        "charter_currency_id": request.form.get("charter_currency_id"),
        "charter_fee": request.form.get("charter_fee"),
        "ship_currency_id": request.form.get("ship_currency_id"),
        "ship_cost": request.form.get("ship_cost"),
        "repayment_currency_id": request.form.get("repayment_currency_id"),
        "repayment": request.form.get("repayment"),
        "interest_currency_id": request.form.get("interest_currency_id"),
        "interest": request.form.get("interest")
    }

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM ship_details WHERE ship_id = %s", (ship_id,))
            exists = cur.fetchone()
            if exists:
                cur.execute("""
                    UPDATE ship_details
                    SET charter_currency_id = %s, charter_fee = %s,
                        ship_currency_id = %s, ship_cost = %s,
                        repayment_currency_id = %s, repayment = %s,
                        interest_currency_id = %s, interest = %s
                    WHERE ship_id = %s
                """, (*data.values(), ship_id))
            else:
                cur.execute("""
                    INSERT INTO ship_details (
                        ship_id,
                        charter_currency_id, charter_fee,
                        ship_currency_id, ship_cost,
                        repayment_currency_id, repayment,
                        interest_currency_id, interest
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (ship_id, *data.values()))

    return redirect(url_for("ship_detail", ship_id=ship_id))
if __name__ == "__main__":
    print("Starting app on port 5000...")
    app.run(host="0.0.0.0", port=5000)
