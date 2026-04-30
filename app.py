import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

BASE = "https://www.snooker.org/res/index.asp"

URLS = {
    "history": BASE + "?template=22",
    "upcoming": BASE + "?template=24",
    "live": BASE + "?template=21",
}


def get_text_rows(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    rows = []

    for tr in soup.find_all("tr"):
        text = tr.get_text(" ", strip=True)
        if len(text) > 10:
            rows.append(text)

    return rows


def parse_history(text):
    pattern = r"(\d{4}-\d{2}-\d{2}).*?([A-Za-z .'\-]+)\s*\[\d+\]\s*(\d+)\s*-\s*(\d+)\s*([A-Za-z .'\-]+)\s*\[\d+\]"
    m = re.search(pattern, text)

    if not m:
        return None

    date = m.group(1)
    player1 = m.group(2).strip()
    score1 = int(m.group(3))
    score2 = int(m.group(4))
    player2 = m.group(5).strip()
    winner = player1 if score1 > score2 else player2

    event_match = re.search(r"([A-Za-z ]+ Championship|[A-Za-z ]+ Open|Masters|Shoot Out|Grand Prix)", text)
    event = event_match.group(1).strip() if event_match else "Snooker Event"

    return {
        "type": "history",
        "date": date,
        "event": event,
        "round": "",
        "player1": player1,
        "player2": player2,
        "score": f"{score1}-{score2}",
        "winner": winner,
        "status": "已结束"
    }


def parse_upcoming(text):
    # 有些 upcoming 行是：Player A v Player B
    m = re.search(r"([A-Za-z .'\-]+)\s+v\s+([A-Za-z .'\-]+)", text)

    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    date = date_match.group(1) if date_match else ""

    event_match = re.search(r"([A-Za-z ]+ Championship|[A-Za-z ]+ Open|Masters|Shoot Out|Grand Prix)", text)
    event = event_match.group(1).strip() if event_match else "即将比赛"

    if m:
        return {
            "type": "upcoming",
            "date": date,
            "event": event,
            "round": "",
            "player1": m.group(1).strip(),
            "player2": m.group(2).strip(),
            "score": "未开始",
            "winner": "",
            "status": "未开始"
        }

    if date:
        return {
            "type": "upcoming",
            "date": date,
            "event": "未公布对阵",
            "round": "",
            "player1": "",
            "player2": "",
            "score": "未开始",
            "winner": "",
            "status": "未公布"
        }

    return None


def collect(mode):
    url = URLS.get(mode, URLS["history"])

    try:
        text_rows = get_text_rows(url)
    except Exception as e:
        return [{
            "type": mode,
            "date": "",
            "event": "数据抓取失败",
            "round": "",
            "player1": "",
            "player2": "",
            "score": "",
            "winner": "",
            "status": str(e)
        }]

    results = []

    for text in text_rows:
        if mode == "history":
            item = parse_history(text)
        else:
            item = parse_upcoming(text)

        if item:
            results.append(item)

    return results[:300]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/matches")
def matches():
    mode = request.args.get("mode", "history")
    return jsonify(collect(mode))


if __name__ == "__main__":
    app.run(debug=True)