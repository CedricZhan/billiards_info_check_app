import re
import requests
from bs4 import BeautifulSoup

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

# 赛事名库：长名字放前面，避免 World Championship / Masters 这种短名字先误命中。
EVENT_NAMES = [
    "Saudi Arabia Snooker Masters",
    "Northern Ireland Open",
    "International Championship",
    "World Seniors Championship",
    "World Senior Championship",
    "Champion of Champions",
    "Players Championship",
    "Tour Championship",
    "World Championship",
    "UK Championship",
    "World Grand Prix",
    "Xi'an Grand Prix",
    "German Masters",
    "European Masters",
    "Scottish Open",
    "English Open",
    "British Open",
    "Welsh Open",
    "Wuhan Open",
    "World Open",
    "China Open",
    "Shoot Out",
    "Masters",
]
EVENT_NAMES = sorted(EVENT_NAMES, key=len, reverse=True)
EVENT_PATTERN = re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(x) for x in EVENT_NAMES) + r")(?![A-Za-z])", re.I)
ROUND_PATTERN = re.compile(r"\b(Final|SF|QF|Semi[- ]final|Quarter[- ]final|Last \d+|Round \d+)\b(?:\s*\(\d+\))?", re.I)

COUNTRIES = {
    "england", "scotland", "wales", "northern ireland", "ireland", "china", "iran", "belgium", "thailand",
    "australia", "hong kong", "germany", "poland", "pakistan", "india", "brazil", "malaysia", "switzerland",
    "saudi arabia", "qatar", "uae", "united arab emirates",
}
BAD_PLAYER_TOKENS = {
    "jan", "feb", "mar", "apr", "april", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "world", "championship", "championships", "snooker", "event", "head to head", "referee", "table",
    "match", "session", "tbc", "bye", "qf", "sf", "final", "z",
}

def fetch_soup(url):
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=25)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def normalise_date(text):
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


def canonical_event(name):
    if not name:
        return ""
    low = name.lower()
    for full in EVENT_NAMES:
        if low == full.lower():
            return full
    return name.strip()


def extract_event(text, fallback="未找到赛事"):
    m = EVENT_PATTERN.search(text or "")
    return canonical_event(m.group(1)) if m else fallback


def extract_round(text):
    m = ROUND_PATTERN.search(text or "")
    if not m:
        return ""
    v = m.group(1).upper().replace("-", " ")
    if v == "QF":
        return "QF"
    if v == "SF":
        return "SF"
    return v.title()


def clean_player(name):
    name = re.sub(r"\[[^\]]*\]", " ", name or "")
    name = re.sub(r"\([^)]*\)", " ", name)
    name = re.sub(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b", " ", name, flags=re.I)
    name = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?Z?\b", " ", name)
    name = re.sub(r"\b20\d{2}\b", " ", name)
    # snooker.org 有些单元格会把 UTC 的 Z、轮次 QF/SF 混进球员名前面。
    name = re.sub(r"^(?:Z\s+)?(?:QF|SF|Final|Semi[- ]final|Quarter[- ]final|Last \d+|Round \d+)\s+", " ", name, flags=re.I)
    name = re.sub(r"\bZ\b", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .,:;|/")
    if not name:
        return "undecided"

    # “S Murphy / J Higgins”这种是候选人，不是确定人员；按需求显示 undecided。
    if "/" in name:
        return "undecided"

    low = name.lower()
    if low in COUNTRIES or low in BAD_PLAYER_TOKENS or low in MONTHS:
        return "undecided"
    if all(w.lower().strip(".'-") in BAD_PLAYER_TOKENS for w in name.split()):
        return "undecided"
    return name


def parse_history_text(text, event_hint="未找到赛事"):
    pattern = r"(\d{4}-\d{2}-\d{2}).*?([A-Za-z .'-]+)\s*\[\d+\]\s*(\d+)\s*-\s*(\d+)\s*([A-Za-z .'-]+)\s*\[\d+\]"
    m = re.search(pattern, text)
    if not m:
        return None
    p1, p2 = clean_player(m.group(2)), clean_player(m.group(5))
    s1, s2 = int(m.group(3)), int(m.group(4))
    return {
        "type": "history", "date": m.group(1), "event": extract_event(text, event_hint), "round": extract_round(text),
        "player1": p1, "player2": p2, "score": f"{s1} - {s2}",
        "winner": p1 if s1 > s2 else p2, "status": "已结束",
    }


def is_noise_cell(cell):
    low = cell.lower().strip()
    return (not cell or low in COUNTRIES or low in {"head to head", "h2h", "-"}
            or low.startswith("referee") or low.startswith("table"))


def parse_row_cells(cells, event_hint="未找到赛事", source="upcoming"):
    text = " ".join(cells)
    event = extract_event(text, event_hint)
    date = normalise_date(text)
    round_name = extract_round(text)

    # Live/history-like score rows: Round, country, Player1, score1, -, score2, country, Player2
    for i in range(len(cells) - 2):
        if cells[i].isdigit() and cells[i + 1] == "-" and cells[i + 2].isdigit():
            left = [c for c in cells[:i] if not is_noise_cell(c)]
            right = [c for c in cells[i + 3:] if not is_noise_cell(c)]
            p1 = clean_player(left[-1] if left else "")
            p2 = clean_player(right[0] if right else "")
            if p1 != "undecided" and p2 != "undecided":
                return {
                    "type": "upcoming", "date": date, "event": event, "round": round_name,
                    "player1": p1, "player2": p2, "score": f"{cells[i]} - {cells[i+2]}", "status": "进行中",
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
    items = []
    current_event = "未找到赛事"

    # 按页面顺序走：遇到标题/说明里的赛事名就记下来，后面的 tr 没有赛事名时用最近的赛事名。
    # 这样保留你原来的表格行解析方式，同时解决“赛事名不在同一行”的问题。
    for node in soup.find_all(["h1", "h2", "h3", "h4", "caption", "p", "div", "tr"]):
        node_text = node.get_text(" ", strip=True)
        found_event = extract_event(node_text, "")
        if found_event:
            current_event = found_event

        if node.name != "tr":
            continue

        cells = [td.get_text(" ", strip=True) for td in node.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if len(cells) < 3:
            continue

        item = parse_row_cells(cells, current_event, source)
        if item:
            key = (item["date"], item["event"], item["round"], item["player1"], item["player2"], item["score"])
            if key not in {(x["date"], x["event"], x["round"], x["player1"], x["player2"], x["score"]) for x in items}:
                items.append(item)
    return items


def collect_history_matches():
    soup = fetch_soup(URLS["history"])
    items = []
    current_event = "未找到赛事"

    for node in soup.find_all(["h1", "h2", "h3", "h4", "caption", "p", "div", "tr"]):
        node_text = node.get_text(" ", strip=True)
        found_event = extract_event(node_text, "")
        if found_event:
            current_event = found_event

        if node.name != "tr":
            continue
        item = parse_history_text(node_text, current_event)
        if item:
            key = (item["date"], item["event"], item["round"], item["player1"], item["player2"], item["score"])
            if key not in {(x["date"], x["event"], x["round"], x["player1"], x["player2"], x["score"]) for x in items}:
                items.append(item)
    return items


def collect(mode):
    try:
        if mode == "history":
            return collect_history_matches()[:300]

        # 保留原版本的未来赛事抓取入口：live + upcoming + order。
        # 只改赛事名来源，不用整页第一个赛事名兜底，避免把 World Championship 套到别的比赛上。
        items = []
        for name in ["live", "upcoming", "order"]:
            try:
                for item in collect_table_matches(URLS[name], name):
                    key = (item["date"], item["event"], item["round"], item["player1"], item["player2"])
                    if key not in {(x["date"], x["event"], x["round"], x["player1"], x["player2"]) for x in items}:
                        items.append(item)
            except Exception:
                continue
        return items[:300]

    except Exception as e:
        return [{"type": mode, "date": "", "event": "数据抓取失败", "round": "", "player1": "undecided", "player2": "undecided", "score": "", "status": str(e)}]
