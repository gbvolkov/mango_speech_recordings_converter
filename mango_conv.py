"""
Utility functions and command-line interface for converting call-recording
HTML files to structured tabular data.

The primary entry point is :func:`parse_call_html`, which accepts a string
containing the raw HTML of a call recording and returns two pandas
DataFrames: one with call metadata and another with one row per
utterance in the dialogue. The module also includes helper functions
for post-processing conversations and a simple example script that
demonstrates reading a directory of HTML files and writing a CSV.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Tuple

import pandas as pd
from bs4 import BeautifulSoup

# Translation of Russian header labels to English column names
LABEL_XLAT = {
    "Номер линии АТС": "line_number",
    "Кто звонил": "caller",
    "С кем говорил": "callee",
    "Длительность": "duration_raw",
}


def _duration_to_seconds(raw: str | None) -> int | None:
    """Convert a duration string into seconds.

    Accepts strings with hours, minutes and seconds separated by colons.
    Non-numeric characters are stripped before processing. Returns
    ``None`` if the input is empty or cannot be parsed.
    """
    if not raw:
        return None
    cleaned = re.sub(r"[^0-9:]", "", raw)
    parts = [int(p) for p in cleaned.split(":") if p]
    if len(parts) == 3:
        h, m, s = parts
        return h * 3600 + m * 60 + s
    if len(parts) == 2:
        m, s = parts
        return m * 60 + s
    return parts[0] if len(parts) == 1 else None


def _clean(td) -> str:
    """Collapse whitespace and newlines from a BeautifulSoup table cell."""
    return " ".join(
        ln.strip() for ln in td.get_text("\n", strip=True).splitlines() if ln.strip()
    )


SEPARATOR = "##"


def parse_call_html(html: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Parse a call‑recording HTML into header and conversation DataFrames.

    Parameters
    ----------
    html : str
        Raw HTML containing a single call recording. The first table
        element is assumed to contain all relevant information.

    Returns
    -------
    (header_df, conversation_df) : Tuple[pandas.DataFrame, pandas.DataFrame]
        ``header_df`` has a single row of metadata. ``conversation_df`` has
        one row per utterance with turn index, role names and text.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        raise ValueError("No table found in the HTML")

    header: dict[str, object] = {}
    dialogue: list[dict[str, object]] = []
    conversation_lines: list[str] = []

    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        text = tds[0].get_text(SEPARATOR).strip()
        # Extract call datetime from the first row
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
        # Standard two-column header row (e.g. "Номер линии АТС:" "123")
        elif len(tds) == 2 and text.endswith(":"):
            label_ru = text.rstrip(":")
            value = tds[1].text.strip()
            header[LABEL_XLAT.get(label_ru, label_ru)] = value
        # Dialogue rows start with a role and include timestamp and text
        elif len(tds) >= 3 and (text.startswith("Сотрудник") or text.startswith("Клиент")):
            conversation_lines.append(
                f"{len(conversation_lines)}. {tds[1].text.strip()}. {text}: {_clean(tds[2])}"
            )
            dialogue.append(
                {
                    "role_ru": text,
                    "role_en": "client" if text == "Клиент" else "employee",
                    "timestamp_local": tds[1].text.strip(),
                    "text": _clean(tds[2]),
                }
            )

    # Post-process header: convert duration and store full conversation
    if "duration_raw" in header:
        header["duration_seconds"] = _duration_to_seconds(header.get("duration_raw"))
    header["conversation"] = "\n".join(conversation_lines)

    header_df = pd.DataFrame([header])
    conversation_df = (
        pd.DataFrame(dialogue)
        .assign(turn_index=lambda d: d.index + 1)
        .loc[:, ["turn_index", "role_ru", "role_en", "timestamp_local", "text"]]
    )
    return header_df, conversation_df


def transpose_conversations(conversation_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot conversation rows into a single wide row.

    Each utterance becomes its own column named ``role_en_turnindex``. For
    example, the first client line becomes ``client_1``, and the second
    employee line becomes ``employee_2``. Useful for tabular exports.
    """
    utterance_cols = {
        f"{row.role_en}_{row.turn_index}": row.text
        for _, row in conversation_df.iterrows()
    }
    return pd.DataFrame([utterance_cols])


def convert_directory(html_dir: Path, csv_output: Path) -> None:
    """Convert all HTML files in a directory into a single CSV summary.

    Parameters
    ----------
    html_dir : pathlib.Path
        Directory containing HTML files to process. ``index.html`` is skipped.
    csv_output : pathlib.Path
        Destination path for the aggregated CSV file.

    Notes
    -----
    This function merges conversation rows with call metadata and writes
    all resulting rows to a CSV. Each utterance appears on its own row.
    """
    final_rows: list[pd.DataFrame] = []
    for file_path in html_dir.iterdir():
        if (
            file_path.name == "index.html"
            or file_path.suffix.lower() != ".html"
        ):
            continue
        with file_path.open("r", encoding="utf-8") as f:
            html = f.read()
        header_df, conv_df = parse_call_html(html)
        merged_df = conv_df.assign(**header_df.iloc[0].to_dict())
        # Order columns: header first
        header_cols = [
            "call_datetime_raw", "call_datetime",
            "line_number", "caller", "callee",
            "duration_raw", "duration_seconds"
        ]
        dialogue_cols = [c for c in merged_df.columns if c not in header_cols]
        merged_df = merged_df[header_cols + dialogue_cols]
        final_rows.append(merged_df)
    if final_rows:
        final_df = pd.concat(final_rows, ignore_index=True)
        csv_output.parent.mkdir(parents=True, exist_ok=True)
        final_df.to_csv(csv_output, index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    # Example usage: iterate over ./data/html and write a summary CSV
    html_path = Path("./data/html")
    csv_path = Path("./data/conversations_full.csv")
    if html_path.is_dir():
        print(f"Processing directory {html_path} → {csv_path}")
        convert_directory(html_path, csv_path)
        print(f"Saved CSV to {csv_path}")
    else:
        print(f"Directory {html_path} does not exist; skipping conversion")