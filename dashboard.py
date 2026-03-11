#!/usr/bin/env python3
import socket
from pathlib import Path

from flask import Flask, jsonify

APP = Flask(__name__)
CONFIG_DIR = Path("/etc/openclaw")


def read_value(name, default=""):
    path = CONFIG_DIR / name
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8").strip()


@APP.route("/")
def index():
    hostname = socket.gethostname()
    wifi_ssid = read_value("wifi_ssid", "unknown")
    return f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>OpenClaw Dashboard</title>
    <style>
        body {{
            margin: 0;
            font-family: "Segoe UI", sans-serif;
            background: #f4efe6;
            color: #2a241d;
        }}

        main {{
            max-width: 720px;
            margin: 48px auto;
            padding: 24px;
        }}

        section {{
            background: #fffdf8;
            border: 1px solid #d9ccb8;
            border-radius: 18px;
            padding: 24px;
            box-shadow: 0 18px 40px rgba(42, 36, 29, 0.08);
        }}

        h1 {{
            margin: 0 0 12px;
        }}

        dl {{
            display: grid;
            grid-template-columns: max-content 1fr;
            gap: 12px 18px;
        }}

        dt {{
            font-weight: 700;
        }}

        a {{
            color: #a64b2a;
        }}
    </style>
</head>
<body>
    <main>
        <section>
            <h1>OpenClaw Dashboard</h1>
            <dl>
                <dt>Hostname</dt>
                <dd>{hostname}</dd>
                <dt>Wi-Fi</dt>
                <dd>{wifi_ssid}</dd>
                <dt>API</dt>
                <dd><a href="/api/status">/api/status</a></dd>
            </dl>
        </section>
    </main>
</body>
</html>"""


@APP.route("/api/status")
def status():
    return jsonify(
        {
            "initialized": (CONFIG_DIR / "initialized").exists(),
            "hostname": socket.gethostname(),
            "wifi_ssid": read_value("wifi_ssid", "unknown"),
            "admin_user": read_value("admin_user", "root"),
            "connection_name": read_value("nm_connection_name", ""),
        }
    )


if __name__ == "__main__":
    APP.run(host="127.0.0.1", port=8080)
