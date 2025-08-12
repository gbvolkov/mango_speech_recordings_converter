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
    return Response(render_template("index_template.html"), mimetype="text/html")


@app.route("/upload", methods=["POST"])
def upload() -> Response:
    """Handle file upload and return a CSV.

    Expects a multipart/form‑data request with a file field named ``file``.
    The uploaded file is interpreted as UTF‑8 HTML. The response is
    returned with a ``Content‑Disposition`` header so that browsers will
    download it directly.
    """
    uploaded_file = request.files.get("file")
    if uploaded_file is None or uploaded_file.filename == "":
        return Response("No file uploaded", status=400)

    try:
        html = uploaded_file.read().decode("utf-8")
    except Exception:
        return Response("Failed to read uploaded file", status=400)

    try:
        header_df, _ = parse_call_html(html)
    except Exception as exc:
        return Response(f"Failed to parse HTML: {exc}", status=400)

    # Write CSV to an in‑memory buffer
    csv_buffer = io.StringIO()
    header_df.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
    csv_buffer.seek(0)

    return Response(
        csv_buffer.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=conversation.csv",
        },
    )


if __name__ == "__main__":
    # Run the Flask development server when executed directly.
    app.run(debug=True)