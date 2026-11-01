"""Собирает даши турниров: config.json + CSV из Google Sheets -> <out>/TourneyDashes/<id>/index.html.

Запуск: python TourneyDashes/collect.py site
Секреты приходят из SECRETS_JSON (весь набор секретов репо) или из обычных переменных окружения.
"""
import csv
import io
import json
import os
import re
import shutil
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MSK = timezone(timedelta(hours=3))
SECRETS = json.loads(os.environ.get("SECRETS_JSON") or "{}")


def secret(value):
    """"$NAME" -> значение секрета NAME."""
    if isinstance(value, str) and value.startswith("$"):
        name = value[1:]
        got = SECRETS.get(name) or os.environ.get(name)
        if not got:
            raise SystemExit(f"Нет секрета {name}")
        return got
    return value


def fetch_csv(src):
    if os.path.exists(src):  # локальный файл для проверки
        text = Path(src).read_text(encoding="utf-8")
    else:
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8")
    return list(csv.reader(io.StringIO(text)))


def cell(row, i):
    return row[i].strip() if i < len(row) else ""


def plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def parse(rows):
    """Лист Main: E — инфа о турнире, F:G — участники по алфавиту и оплата."""
    head = rows[0] if rows else []

    # Квалификация: "Finals'26 Qualifier (2 slots)" -> "Finals'26 Qualifier", "2 слота"
    qual, slots = cell(head, 4), ""
    m = re.match(r"(.*?)\s*\((\d+)\s*slots?\)\s*$", qual, re.I)
    if m:
        qual, n = m.group(1), int(m.group(2))
        slots = f"{n} {plural(n, 'слот', 'слота', 'слотов')}"

    # Инфа из столбца E — до строки «Регистрация» (счётчики считаем сами)
    lines = []
    for row in rows[1:]:
        v = cell(row, 4)
        if v.lower().startswith("регистрация"):
            break
        if v:
            lines.append(re.sub(r"\s+", " ", v))

    info = {"qual": qual, "slots": slots, "address": "", "price": "", "banks": "",
            "phone": "", "recipient": "", "tg": "", "cash": ""}
    for i, v in enumerate(lines):
        low = v.lower()
        if i == 0:
            info["address"] = re.sub(r"^г\.\s*", "", v)
        elif low.startswith("участие"):
            info["price"] = v[len("участие"):].strip().replace("₽", " ₽").replace("  ", " ")
        elif "по номеру" in low:
            info["banks"] = re.sub(r"\s*по номеру.*$", "", v, flags=re.I).replace("/", " / ")
        elif re.fullmatch(r"[\d\s+()\-]{10,}", v):
            d = re.sub(r"\D", "", v)
            d = "7" + d[1:] if len(d) == 11 and d[0] in "78" else d
            info["phone"] = f"+{d[0]} {d[1:4]} {d[4:7]}-{d[7:9]}-{d[9:11]}" if len(d) == 11 else v
            if i + 1 < len(lines):
                info["recipient"] = lines[i + 1]
        elif re.match(r"https?://t\.me/", v):
            info["tg"] = v
        elif low.startswith("наличными"):
            info["cash"] = v

    players = []
    for row in rows[1:]:
        name = cell(row, 5)
        if name:
            players.append([name, cell(row, 6).upper() == "TRUE"])
    return info, players


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "site") / "TourneyDashes"
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(HERE / "cinzel.woff2", out / "cinzel.woff2")
    template = (HERE / "template.html").read_text(encoding="utf-8")
    cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    built = datetime.now(MSK).strftime("%d.%m %H:%M")

    for t in cfg["tourneys"]:
        info, players = parse(fetch_csv(secret(t["csv"])))
        data = {"title": t["title"], "event": t.get("event", ""), "date": t["date"], "cap": t["cap"],
                "built": built, "info": info, "players": players}
        page = template.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False))
        page = page.replace("<title>Турнир</title>", f"<title>{t['title']} {t['date']}</title>")
        d = out / t["id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page, encoding="utf-8")
        print(f"{t['id']}: {len(players)} игроков, оплатили {sum(p[1] for p in players)}")


if __name__ == "__main__":
    main()

# КОНЕЦ ФАЙЛА collect.py
