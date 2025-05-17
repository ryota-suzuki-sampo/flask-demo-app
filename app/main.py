from flask import Flask, render_template
import os

app = Flask(__name__, template_folder="templates")

@app.route("/")
def home():
    return render_template("index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # RailwayのPORT環境変数に従う
    app.run(host="0.0.0.0", port=port)
