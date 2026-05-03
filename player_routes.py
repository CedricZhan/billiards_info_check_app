from flask import Blueprint, render_template, request, jsonify
from services import collect

player_bp = Blueprint("player", __name__)


# 👉 页面（/player?name=xxx）
@player_bp.route("/player")
def player_page():
    name = request.args.get("name", "")
    return render_template("player.html", name=name)


# 👉 数据接口（给 player.html 用）
@player_bp.route("/api/player")
def player_api():
    name = request.args.get("name", "").lower().strip()

    history = collect("history")
    upcoming = collect("upcoming")

    matches = []

    for m in history + upcoming:
        p1 = (m.get("player1") or "").lower()
        p2 = (m.get("player2") or "").lower()

        if name and (name in p1 or name in p2):
            matches.append(m)

    return jsonify(matches)