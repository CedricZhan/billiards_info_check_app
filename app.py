from flask import Flask, jsonify, render_template, request
from services import collect

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/matches")
def matches():
    mode = request.args.get("mode", "history")
    return jsonify(collect(mode))

from player_routes import player_bp
app.register_blueprint(player_bp)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)