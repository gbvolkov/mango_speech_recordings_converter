file_path = "./data/html/2025-07-08__16-37-13__Костерина Кристина__79206761501.html"

from bs4 import BeautifulSoup
from datetime import datetime
import pandas as pd
import re

LABEL_XLAT = {                      # Russian → column name
    "Номер линии АТС": "line_number",
    "Кто звонил":      "caller",
    "С кем говорил":   "callee",
    "Длительность":    "duration_raw",
}

# ---------- small helpers ----------
def _duration_to_seconds(raw: str | None) -> int | None:
    if not raw:
        return None
    raw = re.sub(r'[^0-9:]', '', raw)      # keep only digits & ':'
    parts = [int(p) for p in raw.split(':') if p]
    if   len(parts) == 3:  h, m, s = parts; return h*3600 + m*60 + s
    elif len(parts) == 2:  m, s = parts;   return m*60 + s
    elif len(parts) == 1:  return parts[0]
    return None

def _clean(td) -> str:
    """collapse <br>, strip whitespace"""
    return " ".join(
        ln.strip() for ln in td.get_text("\n", strip=True).splitlines() if ln.strip()
    )


SEPARATOR = "##"

# ---------- main entry point ----------
def parse_call_html(html: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns: header_df (1-row) , conversation_df (N rows)
    """
    soup  = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        raise ValueError("No <table> in the HTML")

    header   : dict = {}
    dialogue : list[dict] = []
    conversation : list[str] = []

    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 1:
            continue
        text = tds[0].get_text(SEPARATOR).strip()
        if text.startswith("Запись разговоров"):
            fields = text.split(SEPARATOR)
            if len(fields) > 1:
                header["call_datetime_raw"] = fields[1]
                try:
                    header["call_datetime"] = datetime.strptime(
                        header["call_datetime_raw"], "%d.%b.%Y %H:%M:%S"
                    )
                except ValueError:
                    header["call_datetime"] = None
        elif len(tds) == 2 and text.endswith(":"):
            label_ru = text.rstrip(":")
            value = tds[1].text.strip()
            header[LABEL_XLAT.get(label_ru, label_ru)] = value
        # ── DIALOGUE ROWS ────────────────────────────────────────────
        elif len(tds) >= 3 and (text.startswith("Сотрудник") or text.startswith("Клиент")):
            conversation_txt = f"{len(conversation)}. {tds[1].text.strip()}. {text}: {_clean(tds[2])}"
            conversation.append(conversation_txt)
            
            dialogue.append({
                "role_ru": text,
                "role_en": "client" if text == "Клиент" else "employee",
                "timestamp_local": tds[1].text.strip(),
                "text": _clean(tds[2]),
            })

    # post-processing for header
    if "duration_raw" in header:
        header["duration_seconds"] = _duration_to_seconds(header["duration_raw"])
        header["converation"] = "\n".join(conversation)

    header_df       = pd.DataFrame([header])
    conversation_df = (
        pd.DataFrame(dialogue)
          .assign(turn_index=lambda d: d.index + 1)
          .loc[:, ["turn_index","role_ru","role_en","timestamp_local","text"]]
    )
    return header_df, conversation_df

def transpose_converstions(conversation_df):
    utterance_cols = {
        f"{row.role_en}_{row.turn_index}": row.text
        for _, row in conversation_df.iterrows()
    }
    return pd.DataFrame([utterance_cols])

# ---------------------------
# Example usage on a file
# ---------------------------

from pathlib import Path
final_df = pd.DataFrame()

html_path = Path("./data/html")
for file_path in html_path.iterdir():
    if file_path.name == "index.html":
        continue
    print(f"processing file {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        html = f.read()
    header_df, conversation_df = parse_call_html(html)
    header_df["file"] = file_path
    #print(header_df)          # header
    #print(conversation_df.head())   # first turns

    #conversation_df = transpose_converstions(conversation_df)
    #print(conversation_df.head())

    merged_df = conversation_df.assign(**header_df.iloc[0].to_dict())

    cols_front = [
        "call_datetime_raw", "call_datetime",
        "line_number", "caller", "callee",
        "duration_raw", "duration_seconds"
    ]
    cols_dialog = [c for c in merged_df.columns if c not in cols_front]
    merged_df = merged_df[cols_front + cols_dialog]
    final_df = pd.concat([final_df, header_df])
    print(f"{file_path} processed.")

csv_path = "data/conversations_short.csv"
final_df.to_csv(csv_path, index=False, encoding="utf-8-sig")