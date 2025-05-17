from flask import Flask, render_template, request, redirect, url_for, send_file
import os
import psycopg2
from datetime import datetime
from io import BytesIO
import openpyxl

app = Flask(__name__, template_folder="templates")

def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

@app.route("/")
def home_redirect():
    return redirect("/ships")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
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

    return render_template("register.html")

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

@app.route("/export_excel", methods=["POST"])
def export_excel():
    ship_ids = request.form.getlist("ship_ids")
    template_file = request.files.get("template_file")

    if not ship_ids or not template_file:
        return "船舶選択とテンプレートファイルの両方が必要です", 400

    # テンプレート読み込み
    wb = openpyxl.load_workbook(template_file)
    if "format" not in wb.sheetnames:
        return "テンプレートに 'format' シートが存在しません", 400

    # 新シート作成
    now_str = datetime.now().strftime("%Y%m%d%H%M")
    ws_template = wb["format"]
    ws_output = wb.copy_worksheet(ws_template)
    ws_output.title = f"Output_{now_str}"

    # DBから対象データ取得
    with get_conn() as conn:
        with conn.cursor() as cur:
            format_ids = tuple(map(int, ship_ids))
            cur.execute(f"""
                SELECT s.id, s.ship_name,
                       cd1.name AS charter_currency, sd.charter_fee,
                       cd2.name AS ship_currency, sd.ship_cost,
                       cd3.name AS repayment_currency, sd.repayment,
                       cd4.name AS interest_currency, sd.interest
                FROM ships s
                LEFT JOIN ship_details sd ON s.id = sd.ship_id
                LEFT JOIN currencies cd1 ON sd.charter_currency_id = cd1.id
                LEFT JOIN currencies cd2 ON sd.ship_currency_id = cd2.id
                LEFT JOIN currencies cd3 ON sd.repayment_currency_id = cd3.id
                LEFT JOIN currencies cd4 ON sd.interest_currency_id = cd4.id
                WHERE s.id IN %s
                ORDER BY s.id
            """, (format_ids,))
            records = cur.fetchall()

    # 4行目から書き込み
    start_row = 4
    for idx, row in enumerate(records, start=1):
        ws_output.cell(row=start_row, column=2, value=idx)                     # B列: 連番
        ws_output.cell(row=start_row, column=3, value=row[1])                 # C列: 船名
        ws_output.cell(row=start_row, column=4, value=row[2])                 # D列: 傭船料通貨
        ws_output.cell(row=start_row, column=5, value=row[3])                 # E列: 傭船料金額
        ws_output.cell(row=start_row, column=6, value=row[4])                 # F列: 船舶費通貨
        ws_output.cell(row=start_row, column=7, value=row[5])                 # G列: 船舶費金額
        ws_output.cell(row=start_row, column=8, value=row[6])                 # H列: 元利金通貨
        ws_output.cell(row=start_row, column=9, value=row[7])                 # I列: 元利金金額

        # J列: 利息（%表示）
        if row[8] is not None:
            cell = ws_output.cell(row=start_row, column=10, value=row[9])
            cell.number_format = '0.00%'

        start_row += 1

    # 出力ファイルをバッファに保存
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"ShipExport_{now_str}.xlsx"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == "__main__":
    print("Starting app on port 5000...")
    app.run(host="0.0.0.0", port=5000)
