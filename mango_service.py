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

import base64

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
    return Response(render_template("index.html"), mimetype="text/html")


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

    processed_count = 0
    error_count = 0
    final_rows: list[pd.DataFrame] = []
    errors: list[dict[str, str]] = []  # store file name and diagnostic message
    for uploaded_file in files:
        # Skip empty file fields
        if uploaded_file is None or uploaded_file.filename == "":
            continue
        try:
            html = uploaded_file.read().decode("utf-8")
        except Exception as exc:
            # Record read errors with diagnostic message
            error_count += 1
            errors.append({"filename": uploaded_file.filename, "message": f"Failed to read: {exc}"})
            continue
        try:
            header_df, _ = parse_call_html(html)
        except Exception as exc:
            # Record parse errors with diagnostic message
            error_count += 1
            errors.append({"filename": uploaded_file.filename, "message": f"Failed to parse HTML: {exc}"})
            continue
        final_rows.append(header_df)
        processed_count += 1

    if not final_rows:
        # All files failed; return a page with zero processed and all errors
        return Response(render_template(
            "result.html",
            processed_count=0,
            error_count=error_count,
            errors=errors,
            csv_data_uri=None
        ), mimetype="text/html")

    final_df = pd.concat(final_rows, ignore_index=True)
    csv_buffer = io.StringIO()
    final_df.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
    csv_buffer.seek(0)
    # Encode CSV as base64 for embedding in a data URI
    csv_bytes = csv_buffer.getvalue().encode("utf-8-sig")
    csv_b64 = base64.b64encode(csv_bytes).decode("ascii")
    data_uri = f"data:text/csv;base64,{csv_b64}"
    return Response(
        render_template(
            "result.html",
            processed_count=processed_count,
            error_count=error_count,
            errors=errors,
            csv_data_uri=data_uri,
        ),
        mimetype="text/html",
    )


if __name__ == "__main__":
    # Run the Flask development server when executed directly.
    app.run(host='0.0.0.0', port=5006, debug=False)