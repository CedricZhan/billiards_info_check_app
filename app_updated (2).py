import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

BASE = "https://www.snooker.org/res/index.asp"
URLS = {
    "history": BASE + "?template=22",
    "upcoming": BASE + "?template=24",
    "live": BASE + "?template=21",
    "order": BASE + "?template=45",
}

MONTHS = {
    "jan": "01", "january": "01", "feb": "02", "february": "02", "mar": "03", "march": "03",
    "apr": "04", "april": "04", "may": "05", "jun": "06", "june": "06", "jul": "07", "july": "07",
    "aug": "08", "august": "08", "sep": "09", "sept": "09", "september": "09", "oct": "10", "october": "10",
    "nov": "11", "november": "11", "dec": "12", "december": "12",
}

# 只返回这个库里的完整赛事名；长名优先，避免 World Senior(s) Championship 被截成 World Championship。
EVENT_NAMES = (
    "Saudi Arabia Snooker Masters",
    "Northern Ireland Open",
    "International Championship",
    "Champion of Champions",
    "World Seniors Snooker Championship",
    "World Senior Snooker Championship",
    "World Seniors Championship",
    "World Senior Championship",
    "World Snooker Championship",
    "Halo World Championship",
    "World Championship",
    "UK Championship",
    "World Grand Prix",
    "Players Championship",
    "Tour Championship",
    "Scottish Open",
    "European Masters",
    "German Masters",
    "Welsh Open",
    "English Open",
    "British Open",
    "Wuhan Open",
    "Xi'an Grand Prix",
    "China Open",
    "World Open",
    "Shoot Out",
    "Masters",
)
EVENT_ALIASES = {
    "world seniors snooker championship": "World Senior Championship",
    "world senior snooker championship": "World Senior Championship",
    "world seniors championship": "World Senior Championship",
}
EVENT_CANONICAL = {name.lower(): name for name in EVENT_NAMES}
EVENT_PATTERN = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(x) for x in sorted(EVENT_NAMES, key=len, reverse=True)) + r")(?![A-Za-z])",
    re.I,
)
ROUND_PATTERN = re.compile(r"\b(Final|SF|QF|Semi[- ]finals?|Quarter[- ]finals?|Last \d+|Round \d+|Rd \d+)\b(?:\s*\(\d+\))?", re.I)

COUNTRIES = {
    "england", "scotland", "wales", "northern ireland", "ireland", "china", "iran", "belgium", "thailand",
    "australia", "hong kong", "germany", "poland", "pakistan", "india", "brazil", "malaysia", "switzerland",
    "malta", "egypt", "canada", "israel", "cyprus", "ukraine", "austria", "france", "spain"
}
BAD_PLAYER_TOKENS = {
    "jan", "feb", "mar", "apr", "april", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "world", "championship", "snooker", "event", "head to head", "details", "referee", "table", "match", "session",
    "tbc", "bye", "z", "qf", "sf", "final", "semi final", "semi finals", "quarter final", "quarter finals", "rd 1",
}


def fetch_soup(url):
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=25)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def normalise_date(text):
    text = text or ""
    m = re.search(r"(20\d{2})-(\d{2})-(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\s*(\d{1,2})\s+([A-Za-z]{3,9})\s+(20\d{2})\b", text, re.I)
    if m and m.group(2).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(2).lower()]}-{int(m.group(1)):02d}"
    m = re.search(r"\b([A-Za-z]{3,9})\s+(\d{1,2})\s+(20\d{2})\b", text, re.I)
    if m and m.group(1).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(1).lower()]}-{int(m.group(2)):02d}"
    return ""


def extract_event(text, fallback=""):
    m = EVENT_PATTERN.search(text or "")
    if not m:
        return fallback
    matched = re.sub(r"\s+", " ", m.group(1).strip())
    low = matched.lower()
    return EVENT_ALIASES.get(low) or EVENT_CANONICAL.get(low, matched)


def extract_round(text):
    m = ROUND_PATTERN.search(text or "")
    if not m:
        return ""
    v = m.group(1).upper().replace("-", " ")
    if v in {"QF", "SF"}:
        return v
    if v.startswith("RD "):
        return "Round " + v.split()[-1]
    return v.title()


def clean_player(name):
    name = re.sub(r"\[[^\]]*\]", " ", name or "")
    name = re.sub(r"\([^)]*\)", " ", name)
    name = re.sub(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b", " ", name, flags=re.I)
    name = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?Z?\b", " ", name, flags=re.I)
    name = re.sub(r"\b20\d{2}\b", " ", name)
    # 删除误混进球员名里的时区/轮次字段，比如 “Z QF John Higgins”。
    name = re.sub(r"\b(?:Z|QF|SF|Final|Semi[- ]finals?|Quarter[- ]finals?|Round \d+|Rd \d+|Last \d+)\b", " ", name, flags=re.I)
    name = re.sub(r"\s+", " ", name).strip(" .,:;|/")
    if not name or "/" in name:
        return "undecided"

    low = name.lower().strip()
    if low in COUNTRIES or low in MONTHS or low in BAD_PLAYER_TOKENS:
        return "undecided"
    if all(w.lower().strip(".'-") in BAD_PLAYER_TOKENS for w in name.split()):
        return "undecided"
    return name


def is_noise_cell(cell):
    low = re.sub(r"\s+", " ", (cell or "").lower().strip(" .,:;|/"))
    return (
        not low
        or low in COUNTRIES
        or low in MONTHS
        or low in BAD_PLAYER_TOKENS
        or low in {"head to head", "h2h", "v", "vs", "-", "z"}
        or bool(ROUND_PATTERN.fullmatch(cell or ""))
        or bool(re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?z?", low))
        or low.startswith("referee")
        or low.startswith("table")
    )


def extract_event_from_row(tr, fallback=""):
    """只从当前行文字/链接文字取赛事名，不打开 H2H 链接，避免把旧赛事误套到当前比赛。"""
    text = tr.get_text(" ", strip=True)
    event = extract_event(text, "")
    if event:
        return event
    for a in tr.find_all("a", href=True):
        link_text = " ".join([a.get_text(" ", strip=True), a.get("title", ""), a.get("href", "")])
        event = extract_event(link_text, "")
        if event:
            return event
    return fallback


def build_score_item(date, event, round_name, p1, p2, s1, s2, status, item_type="history"):
    p1, p2 = clean_player(p1), clean_player(p2)
    item = {
        "type": item_type,
        "date": date,
        "event": event or "未找到赛事",
        "round": round_name,
        "player1": p1,
        "player2": p2,
        "score": f"{int(s1)} - {int(s2)}",
        "status": status,
    }
    if item_type == "history":
        item["winner"] = p1 if int(s1) > int(s2) else p2
    return item


def parse_history_text(text, event_hint=""):
    date = normalise_date(text)
    if not date:
        return None
    pattern = r"(?:20\d{2}-\d{2}-\d{2}|\b\d{1,2}\s+[A-Za-z]{3,9}\s+20\d{2}\b).*?([A-Za-z .'-]+)\s*\[\d+\]\s*(\d+)\s*-\s*(\d+)\s*([A-Za-z .'-]+)\s*\[\d+\]"
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    event = extract_event(text, event_hint) or event_hint or "未找到赛事"
    return build_score_item(date, event, extract_round(text), m.group(1), m.group(4), m.group(2), m.group(3), "已结束", "history")


def parse_history_row(tr, event_hint=""):
    cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
    cells = [c for c in cells if c]
    text = tr.get_text(" ", strip=True)
    event = extract_event_from_row(tr, event_hint) or event_hint or ""
    date = normalise_date(text)
    round_name = extract_round(text)

    # 按列找 score，左右最近的非噪声字段就是球员；这样不会把 Z/QF 带进球员名。
    for i in range(len(cells) - 2):
        if cells[i].isdigit() and cells[i + 1] == "-" and cells[i + 2].isdigit():
            left = [c for c in cells[:i] if not is_noise_cell(c)]
            right = [c for c in cells[i + 3:] if not is_noise_cell(c)]
            p1 = left[-1] if left else ""
            p2 = right[0] if right else ""
            if date and p1 and p2:
                return build_score_item(date, event or "未找到赛事", round_name, p1, p2, cells[i], cells[i + 2], "已结束", "history")

    return parse_history_text(text, event)


def parse_row_cells(cells, event_hint="", source="upcoming"):
    text = " ".join(cells)
    event = extract_event(text, event_hint) or event_hint or "未找到赛事"
    date = normalise_date(text)
    round_name = extract_round(text)

    # Live score rows: Round, country, Player1, score1, -, score2, country, Player2
    for i in range(len(cells) - 2):
        if cells[i].isdigit() and cells[i + 1] == "-" and cells[i + 2].isdigit():
            left = [c for c in cells[:i] if not is_noise_cell(c)]
            right = [c for c in cells[i + 3:] if not is_noise_cell(c)]
            p1 = clean_player(left[-1] if left else "")
            p2 = clean_player(right[0] if right else "")
            if p1 != "undecided" and p2 != "undecided":
                return {
                    "type": "upcoming", "date": date, "event": event, "round": round_name,
                    "player1": p1, "player2": p2, "score": f"{cells[i]} - {cells[i + 2]}", "status": "进行中",
                }

    # Upcoming/order rows: Player1, v, Player2, date
    for i, c in enumerate(cells):
        if c.lower().strip(". ") in {"v", "vs"}:
            left = [x for x in cells[:i] if not is_noise_cell(x)]
            right = [x for x in cells[i + 1:] if not is_noise_cell(x)]
            p1 = clean_player(left[-1] if left else "")
            p2 = clean_player(right[0] if right else "")
            if p1 == "undecided" and p2 == "undecided" and not date:
                return None
            return {
                "type": "upcoming", "date": date, "event": event, "round": round_name,
                "player1": p1, "player2": p2, "score": "未开始", "status": "未公布" if p1 == p2 == "undecided" else "未开始",
            }

    return None


def collect_table_matches(url, source="upcoming"):
    soup = fetch_soup(url)
    page_event = extract_event(soup.title.get_text(" ", strip=True) if soup.title else "", "")
    current_event = page_event
    items = []
    seen = set()

    for tr in soup.find_all("tr"):
        row_text = tr.get_text(" ", strip=True)
        row_event = extract_event(row_text, "")
        # 只有赛事标题行才更新 current_event；比赛行里的旧 H2H/文本不能覆盖当前赛事。
        if row_event and not re.search(r"\b(?:v|vs|-)\b", row_text, re.I) and not re.search(r"\b\d+\s*-\s*\d+\b", row_text):
            current_event = row_event

        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if len(cells) < 3:
            continue

        # 先拿原始行里的赛事名，再清噪声解析球员。
        link_event = extract_event_from_row(tr, "")
        event_hint = link_event or current_event or page_event or ""
        clean_cells = [c for c in cells if not is_noise_cell(c)]
        item = parse_row_cells(clean_cells, event_hint, source)
        if item:
            key = (item["date"], item["event"], item["round"], item["player1"], item["player2"], item["score"])
            if key not in seen:
                seen.add(key)
                items.append(item)
    return items


def collect(mode):
    try:
        if mode == "history":
            soup = fetch_soup(URLS["history"])
            items = []
            seen = set()
            current_event = extract_event(soup.title.get_text(" ", strip=True) if soup.title else "", "")
            for tr in soup.find_all("tr"):
                row_text = tr.get_text(" ", strip=True)
                row_event = extract_event(row_text, "")
                if row_event and not re.search(r"\b\d+\s*-\s*\d+\b", row_text):
                    current_event = row_event
                item = parse_history_row(tr, current_event)
                if item:
                    key = (item["date"], item["event"], item["round"], item["player1"], item["player2"], item["score"])
                    if key not in seen:
                        seen.add(key)
                        items.append(item)
            return items[:300]

        # 不用历史胜者去“猜”未来赛程；只采集官网 upcoming/order/live 里明确写出的对阵。
        items = []
        seen = set()
        for name in ["live", "upcoming", "order"]:
            try:
                for item in collect_table_matches(URLS[name], name):
                    key = (item["date"], item["event"], item["round"], item["player1"], item["player2"])
                    if key not in seen:
                        seen.add(key)
                        items.append(item)
            except Exception:
                continue
        return items[:300]

    except Exception as e:
        return [{"type": mode, "date": "", "event": "数据抓取失败", "round": "", "player1": "undecided", "player2": "undecided", "score": "", "status": str(e)}]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/matches")
def matches():
    mode = request.args.get("mode", "history")
    return jsonify(collect(mode))


if __name__ == "__main__":
    app.run(debug=True)
