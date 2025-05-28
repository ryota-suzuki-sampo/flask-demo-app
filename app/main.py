from flask import Flask, render_template, request, redirect, url_for, send_file, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg2
from datetime import datetime, timedelta
from io import BytesIO
import openpyxl
from openpyxl import load_workbook

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "secret-key")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# --- DB接続 ---
def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

# --- User クラス ---
class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

    @staticmethod
    def get_by_username(username):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, username, password_hash FROM users WHERE username = %s", (username,))
                row = cur.fetchone()
                if row:
                    return User(*row)
        return None

    @staticmethod
    def get(user_id):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, username, password_hash FROM users WHERE id = %s", (user_id,))
                row = cur.fetchone()
                if row:
                    return User(*row)
        return None

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.get_by_username(username)
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("list_ships"))
        flash("ユーザー名またはパスワードが正しくありません")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("ログアウトしました")
    return redirect(url_for("login"))

@app.route("/")
def home_redirect():
    return redirect("/ships")

@app.route("/register", methods=["GET", "POST"])
@login_required
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
@login_required
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
                       interest_currency_id, interest,
                       loan_balance_currency_id,
                       loan_balance
                FROM ship_details WHERE ship_id = %s
            """, (ship_id,))
            detail = cur.fetchone()

            # 🚨 安全に interest を %表示変換（=100倍）
            if detail:
                detail = list(detail)
                if len(detail) >= 8 and detail[7] is not None:
                    detail[7] = round(detail[7] * 100, 2)

    return render_template("ship_detail.html",
                           ship_id=ship_id,
                           ship_name=ship[0],
                           currencies=currencies,
                           detail=detail,
                           edit=edit_mode)


@app.route("/ships/<int:ship_id>/update", methods=["POST"])
def update_ship_detail(ship_id):
    interest_input = request.form.get("interest")
    interest = float(interest_input) / 100 if interest_input else None

    data = {
        "charter_currency_id": request.form.get("charter_currency_id"),
        "charter_fee": request.form.get("charter_fee"),
        "ship_currency_id": request.form.get("ship_currency_id"),
        "ship_cost": request.form.get("ship_cost"),
        "repayment_currency_id": request.form.get("repayment_currency_id"),
        "repayment": request.form.get("repayment"),
        "interest_currency_id": request.form.get("interest_currency_id"),
        "interest": interest,
        "loan_balance_currency_id": request.form.get("loan_balance_currency_id"),
        "loan_balance": request.form.get("loan_balance")
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
                        interest_currency_id = %s, interest = %s,
                        loan_balance_currency_id = %s, loan_balance = %s
                    WHERE ship_id = %s
                """, (*data.values(), ship_id))
            else:
                cur.execute("""
                    INSERT INTO ship_details (
                        ship_id,
                        charter_currency_id, charter_fee,
                        ship_currency_id, ship_cost,
                        repayment_currency_id, repayment,
                        interest_currency_id, interest, loan_balance_currency_id, loan_balance 
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
    ws_template.sheet_view.tabSelected = False
    wb.active = wb.index(ws_output)

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
                       cd5.name AS loan_currency, sd,loan_balance
                FROM ships s
                LEFT JOIN ship_details sd ON s.id = sd.ship_id
                LEFT JOIN currencies cd1 ON sd.charter_currency_id = cd1.id
                LEFT JOIN currencies cd2 ON sd.ship_currency_id = cd2.id
                LEFT JOIN currencies cd3 ON sd.repayment_currency_id = cd3.id
                LEFT JOIN currencies cd4 ON sd.interest_currency_id = cd4.id
                LEFT JOIN currencies cd5 ON sd.loan_balance_currency_id = cd5.id
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
        if row[9] is not None:
            cell = ws_output.cell(row=start_row, column=10, value=row[9])

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

@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_pw = request.form["current_password"]
        new_pw = request.form["new_password"]
        confirm_pw = request.form["confirm_password"]

        user = current_user

        if not check_password_hash(user.password_hash, current_pw):
            flash("現在のパスワードが正しくありません")
        elif new_pw != confirm_pw:
            flash("新しいパスワードが一致しません")
        else:
            new_hash = generate_password_hash(new_pw)
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, user.id))
            flash("パスワードを変更しました")
            return redirect(url_for("list_ships"))

    return render_template("change_password.html")

@app.route('/aggregate_start', methods=['GET'])
@login_required
def aggregate_start():
    now = datetime.now()
    return render_template('aggregate_start.html', now=now)

@app.route('/api/ship_names', methods=['POST'])
@login_required
def api_ship_names():
    ship_ids = request.json.get('ship_ids', [])
    if not ship_ids:
        return jsonify([])
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ship_name FROM ships WHERE id = ANY(%s) ORDER BY id",
                (list(map(int, ship_ids)),)
            )
            rows = cur.fetchall()
    return jsonify([r[0] for r in rows])

@app.route('/export_aggregated_excel', methods=['POST'])
@login_required
def export_aggregated_excel():
    # フォームデータ取得
    start_month   = request.form['start_month']      # "2025-05"
    template_file = request.files['template_file']   # アップロードされた Excel
    ship_ids      = request.form.getlist('ship_ids') # ['1','2',...]

    if not ship_ids:
        return redirect(url_for('aggregate_start'))

    ids = list(map(int, ship_ids))

    # 1) 傭船料合計
    sql_charter = """
        SELECT cd.name AS currency, COALESCE(SUM(sd.charter_fee), 0) AS total
          FROM ship_details sd
          JOIN currencies cd ON sd.charter_currency_id = cd.id
         WHERE sd.ship_id = ANY(%s)
         GROUP BY cd.name
    """
    # 2) 船舶費合計
    sql_cost = """
        SELECT cd.name AS currency, COALESCE(SUM(sd.ship_cost), 0) AS total
          FROM ship_details sd
          JOIN currencies cd ON sd.ship_currency_id = cd.id
         WHERE sd.ship_id = ANY(%s)
         GROUP BY cd.name
    """
    # 3) 返済額合計
    sql_repay = """
        SELECT cd.name AS currency, COALESCE(SUM(sd.repayment), 0) AS total
          FROM ship_details sd
          JOIN currencies cd ON sd.repayment_currency_id = cd.id
         WHERE sd.ship_id = ANY(%s)
         GROUP BY cd.name
    """
    # 4) 支払利息平均（小数→パーセントに変換）
    sql_interest = """
        SELECT cd.name AS currency, AVG(sd.interest) AS avg_val
          FROM ship_details sd
          JOIN currencies cd ON sd.interest_currency_id = cd.id
         WHERE sd.ship_id = ANY(%s)
         GROUP BY cd.name
    """
    # 5) 融資残高合計
    sql_loan = """
        SELECT cd.name AS currency, COALESCE(SUM(sd.loan_balance), 0) AS total
          FROM ship_details sd
          JOIN currencies cd ON sd.loan_balance_currency_id = cd.id
         WHERE sd.ship_id = ANY(%s)
         GROUP BY cd.name
    """

    # データ取得
    charter_totals = {}
    cost_totals    = {}
    repay_totals   = {}
    interest_avgs  = {}
    loan_totals    = {}
    ship_names     = []

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_charter,  (ids,))
            charter_totals = dict(cur.fetchall())
            print("CHARTER:", charter_totals)

            cur.execute(sql_cost,     (ids,))
            cost_totals    = dict(cur.fetchall())
            print("COST:", cost_totals)

            cur.execute(sql_repay,    (ids,))
            repay_totals   = dict(cur.fetchall())
            print("REPAY:", repay_totals)

            cur.execute(sql_interest, (ids,))
            interest_avgs  = dict(cur.fetchall())
            print("INTEREST AVG:", interest_avgs)

            cur.execute(sql_loan,     (ids,))
            loan_totals    = dict(cur.fetchall())
            print("LOAN:", loan_totals)

            cur.execute(sql_names,    (ids,))
            ship_names = [r[0] for r in cur.fetchall()]
            print("SHIP NAMES:", ship_names)

    # Excel 読み込み
    wb = load_workbook(template_file.stream)
    buf = BytesIO()

    # 通貨コード一覧
    currencies = ['USD', 'CHF', 'XEU']

    for code in currencies:
        sheet_name = f"収支合計_預金管理_{code}"
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]

        # ■ 傭船料：E11～P11
        charter = charter_totals.get(code, 0)
        ws['E7'] = start_month
        for col in range(5, 17):
            ws.cell(row=11, column=col, value=charter)

        # ■ 船舶費：USD→14行目 / その他→57行目
        cost = cost_totals.get(code, 0)
        row_cost = 14 if code == 'USD' else 57
        for col in range(5, 17):
            ws.cell(row=row_cost, column=col, value=cost)

        # ■ 返済額：USD→30行目 / その他→73行目
        repay = repay_totals.get(code, 0)
        row_repay = 30 if code == 'USD' else 73
        for col in range(5, 17):
            ws.cell(row=row_repay, column=col, value=repay)

        # ■ 支払利息（平均値×100で％表記）：USD→33行目 / その他→76行目
        avg_interest = interest_avgs.get(code, 0) * 100
        row_int = 33 if code == 'USD' else 76
        for col in range(5, 17):
            ws.cell(row=row_int, column=col, value=avg_interest)

        # ■ 融資残高：USD→D34 / その他→D77
        loan = loan_totals.get(code, 0)
        row_loan = 34 if code == 'USD' else 77
        ws.cell(row=row_loan, column=4, value=loan)

        # 船舶名リスト：S40 以降
        r = 40
        for name in ship_names:
            ws.cell(row=r, column=19, value=name)
            r += 1

    # バッファに保存して返却
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=template_file.filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

if __name__ == "__main__":
    print("Starting app on port 5000...")
    app.run(host="0.0.0.0", port=5000)
