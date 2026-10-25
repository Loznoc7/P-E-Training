"""Build a client's training page for one week from their Google Doc program.

usage: python3 builder.py DOC.json TEMPLATE.html OUT.html DD/MM [--standalone]
                          [--title "Page title"] [--name "Header name"]
  DOC.json      the Google Docs read_doc result (the JSON object with "tabs";
                a wrapper {"content": {...}} is accepted too)
  TEMPLATE.html the page template containing the tokens __DATA__, __TITLE__, __NAME__
  DD/MM         start date of the week to show (the Monday), e.g. 02/11
  --standalone  wrap as a complete HTML document (for GitHub Pages / own hosting)
  --title       browser-tab title (default "P&E Training")
  --name        name shown at the top of the page (default "Pina & Ermira")
Exit code 2 when the doc has no week starting on that date.
"""
import html as _html, json, re, sys

def load(path):
    d = json.load(open(path))
    return d.get("content", d)

def ptext(p):
    return "".join(r.get("textRun", {}).get("content", "") for r in p["paragraph"]["elements"]).rstrip("\n")

def runs(p):
    out = []
    for r in p["paragraph"]["elements"]:
        t = r.get("textRun")
        if not t: continue
        txt = t["content"].replace("\n", "")
        if not txt: continue
        st = t.get("textStyle", {})
        seg = {"t": txt}
        if st.get("link", {}).get("url"): seg["u"] = st["link"]["url"]
        if st.get("bold"): seg["b"] = 1
        if out and out[-1].get("u") == seg.get("u") and out[-1].get("b") == seg.get("b"):
            out[-1]["t"] += txt
        else:
            out.append(seg)
    return [{k: v for k, v in s.items() if k != "b"} for s in out]

SCHEME = re.compile(r"^(\d+ rounds of:|\d+ sets of|Every |Amrap|AMRAP|Ladder|EMOM|Emom|For [Tt]ime|\d+\" on|2-4-6)")
NOTE = re.compile(r"^(Rest|Pick|add a little|same weight|heavier than|Add \d)", re.I)
QTY = re.compile(r"^((?:I{1,3}|IV|V|VI) - |[\d\"'+x]+(?:m)? )")
HEAD = re.compile(r"^(.+?) - (\d+)'\s*(.*)$")

def strip_prefix(segs, n):
    out = []
    for s in segs:
        if n <= 0: out.append(s); continue
        if len(s["t"]) <= n: n -= len(s["t"]); continue
        out.append({**s, "t": s["t"][n:]}); n = 0
    return out

def classify(p):
    txt = ptext(p).strip()
    segs = runs(p)
    if txt.lower() == "-then-": return {"k": "then"}
    if NOTE.match(txt): return {"k": "note", "s": segs}
    if SCHEME.match(txt): return {"k": "scheme", "s": segs}
    m = QTY.match(txt)
    q = m.group(1).strip().rstrip(" -").strip() if m else ""
    return {"k": "ex", "q": q, "s": strip_prefix(segs, m.end()) if m else segs}

def kind(name):
    n = name.upper()
    if "WARM" in n: return "warm"
    if "STRENGTH" in n: return "str"
    if "COOL" in n: return "cool"
    return "cond"

def cell_blocks(cell):
    blocks, cur = [], None
    for p in cell["content"]:
        if "paragraph" not in p: continue
        txt = ptext(p).strip()
        if not txt: continue
        m = HEAD.match(txt)
        if m and (cur is None or txt.upper().startswith(("WARM", "STRENGTH", "COOL", "CARDIO", "FULL", "CONDITION", "HIIT", "CORE", "FINISHER"))):
            name = m.group(1).strip()
            name = name if not name.isupper() else name.title().replace("Hiit", "HIIT")
            cur = {"name": name, "kind": kind(name), "min": int(m.group(2)), "lines": []}
            if m.group(3): cur["sub"] = m.group(3).strip()
            blocks.append(cur)
        elif cur is not None:
            cur["lines"].append(classify(p))
    return blocks

def find_week(doc, ddmm):
    body = doc["tabs"][0]["documentTab"]["body"]["content"]
    header = None
    for e in body:
        if "paragraph" in e:
            m = re.search(r"Week\s+(\d+)\s+(\d{1,2}/\d{1,2})\s*-\s*(\d{1,2}/\d{1,2})", ptext(e))
            if m: header = m
        elif "table" in e and header:
            d1, d2 = header.group(2), ("%02d/%02d" % tuple(int(x) for x in ddmm.split("/")))
            if "%02d/%02d" % tuple(int(x) for x in d1.split("/")) == d2:
                return int(header.group(1)), header.group(2) + " - " + header.group(3), e["table"]
            header = None
    return None

def build(doc, ddmm):
    found = find_week(doc, ddmm)
    if not found: return None
    n, dates, table = found
    rows = table["tableRows"]
    titles = [ptext(c["content"][0]) for c in rows[0]["tableCells"]]
    days = []
    for c, t in enumerate(titles):
        m = re.match(r"(DAY\s*\d+)\s*-\s*(.+)", t.strip(), re.I)
        if m: label, title = m.group(1).title(), m.group(2).title()
        elif re.match(r"^DAY\s*\d+$", t.strip(), re.I): label, title = t.strip().title(), ""
        else: label, title = "Day %d" % (c + 1), t.strip().title()
        blocks = []
        for r in range(1, len(rows)):
            blocks += cell_blocks(rows[r]["tableCells"][c])
        days.append({"label": label, "title": title, "blocks": blocks})
    return {"n": n, "dates": dates, "days": days}

STANDALONE_HEAD = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
    '<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
    'body{margin:0;font:14px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}img{max-width:100%}'
    '[hidden]{display:none!important}</style></head><body>')

if __name__ == "__main__":
    # optional 5th argument: --standalone wraps the page as a complete HTML document (for GitHub Pages)
    doc_path, tpl, out, ddmm = sys.argv[1:5]
    rest = sys.argv[5:]
    standalone = "--standalone" in rest
    def opt(flag, default):
        return rest[rest.index(flag) + 1] if flag in rest and rest.index(flag) + 1 < len(rest) else default
    title, name = opt("--title", "P&E Training"), opt("--name", "Pina & Ermira")
    data = build(load(doc_path), ddmm)
    if data is None:
        print("NO_WEEK_FOR", ddmm); sys.exit(2)
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    html = (open(tpl).read().replace("__TITLE__", _html.escape(title)).replace("__NAME__", _html.escape(name))
            .replace("__DATA__", payload))
    if standalone:
        html = STANDALONE_HEAD + html + "</body></html>\n"
    open(out, "w").write(html)
    print("BUILT week", data["n"], data["dates"], [len(d["blocks"]) for d in data["days"]])
