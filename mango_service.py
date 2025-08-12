"""
Simple web service for converting call-recording HTML files into CSV.

This module exposes a very small Flask application with two routes:

* GET `/` – serves a one‑page HTML client containing a file upload form.
* POST `/upload` – accepts an HTML file, parses it using the built‑in
  ``parse_call_html`` function and returns the conversation data as a CSV
  download.

To run the service locally install the dependencies and execute this file:

```bash
pip install flask pandas beautifulsoup4
python mango_service.py
```

You can then open a browser at ``http://localhost:5000/`` and upload
your call‑recording HTML file. The server will respond with a CSV file
containing both the header metadata and individual conversation rows.
"""

from __future__ import annotations

import io

from flask import Flask, Response, request, render_template
import pandas as pd

# Import the parser from the existing module rather than re‑defining it here.
from mango_conv import parse_call_html

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Parsing utilities
#
# The parsing logic lives in the ``mango_conv`` module. This service
# imports ``parse_call_html`` directly from that module to avoid
# duplication and to ensure any bug fixes in ``mango_conv.py`` apply
# automatically here.


# ---------------------------------------------------------------------------
# Web routes

# The index page is now served from a Jinja template located in the
# ``templates`` directory. See ``templates/index.html`` for the
# corresponding markup.


@app.route("/", methods=["GET"])
def index() -> Response:
    """Serve the simple one‑page HTML client from a template."""
    return Response(render_template("index_multi.html"), mimetype="text/html")


@app.route("/upload", methods=["POST"])
def upload() -> Response:
    """Handle one or more file uploads and return a combined CSV.

    This endpoint accepts a multipart/form‑data request with one or more
    file fields named ``files``. Each uploaded file is interpreted as
    UTF‑8 HTML. All conversations are parsed and merged into a single
    DataFrame. The response contains a CSV download with one row per
    utterance (conversation) across all uploaded files.
    """
    # Retrieve the list of uploaded files. ``getlist`` returns an empty list
    # when the key does not exist.
    files = request.files.getlist("files")
    if not files:
        return Response("No files uploaded", status=400)

    final_rows: list[pd.DataFrame] = []
    for uploaded_file in files:
        # Skip empty file fields
        if uploaded_file is None or uploaded_file.filename == "":
            continue
        try:
            html = uploaded_file.read().decode("utf-8")
        except Exception:
            return Response(f"Failed to read uploaded file {uploaded_file.filename}", status=400)
        try:
            header_df, _ = parse_call_html(html)
        except Exception as exc:
            return Response(f"Failed to parse HTML ({uploaded_file.filename}): {exc}", status=400)

        # Merge conversation and header information so each utterance carries
        # the call metadata. Header values are broadcast across all rows.
        final_rows.append(header_df)

    if not final_rows:
        return Response("No valid files were uploaded", status=400)

    final_df = pd.concat(final_rows, ignore_index=True)
    csv_buffer = io.StringIO()
    final_df.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
    csv_buffer.seek(0)

    return Response(
        csv_buffer.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=conversations.csv",
        },
    )


if __name__ == "__main__":
    # Run the Flask development server when executed directly.
    app.run(host='0.0.0.0', port=5004, debug=False)