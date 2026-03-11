#!/usr/bin/env python3
import logging
import os
import pwd
import re
import subprocess
import time
from pathlib import Path
from threading import Lock, Thread

from flask import Flask, jsonify, request, send_file

APP = Flask(__name__)

CONFIG_DIR = Path("/etc/openclaw")
INIT_FILE = CONFIG_DIR / "initialized"
ADMIN_USER_FILE = CONFIG_DIR / "admin_user"
HOSTNAME_FILE = CONFIG_DIR / "device_hostname"
SSID_FILE = CONFIG_DIR / "wifi_ssid"
CONNECTION_FILE = CONFIG_DIR / "nm_connection_name"
SETUP_PAGE = Path("/opt/openclaw/templates/setup.html")
NGINX_ACTIVE_SNIPPET = Path("/etc/nginx/snippets/openclaw-active-location.conf")
NGINX_ONBOARDING_SNIPPET = Path("/etc/nginx/snippets/openclaw-onboarding.conf")
NGINX_DASHBOARD_SNIPPET = Path("/etc/nginx/snippets/openclaw-dashboard.conf")
LOG_FILE = Path("/var/log/openclaw/onboarding.log")
WLAN_IF = "wlan0"
AP_CIDR = "192.168.4.1/24"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
LOGGER = logging.getLogger("openclaw-onboarding")
PROVISIONING_LOCK = Lock()
PROVISIONING_STATE = {"status": "idle", "message": ""}


def run_command(command, *, input_text=None):
    LOGGER.info("Running command: %s", " ".join(command))
    return subprocess.run(
        command,
        input=input_text,
        capture_output=True,
        text=True,
        check=True,
    )


def optional_command(command):
    try:
        run_command(command)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        LOGGER.warning("Optional command failed: %s; %s", " ".join(command), stderr)


def user_exists(username):
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def select_admin_user():
    requested = os.environ.get("OPENCLAW_ADMIN_USER")
    if requested and user_exists(requested):
        return requested
    if user_exists("openclaw"):
        return "openclaw"
    return "root"


def validate_hostname(hostname):
    if not hostname:
        return "openclaw"
    normalized = hostname.strip().lower()
    if len(normalized) > 63:
        raise ValueError("hostname too long")
    if not re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?", normalized):
        raise ValueError("hostname must contain only lowercase letters, digits, and hyphens")
    return normalized


def validate_payload(form_data):
    ssid = form_data.get("ssid", "").strip()
    wifi_password = form_data.get("wifi_password", "")
    admin_password = form_data.get("admin_password", "")
    hostname = validate_hostname(form_data.get("hostname", "openclaw"))

    if not ssid:
        raise ValueError("wifi ssid is required")
    if len(admin_password) < 8:
        raise ValueError("admin password must be at least 8 characters")

    return {
        "ssid": ssid,
        "wifi_password": wifi_password,
        "admin_password": admin_password,
        "hostname": hostname,
    }


def connection_name_for_ssid(ssid):
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", ssid).strip("-")
    slug = slug[:40] or "wifi"
    return f"openclaw-client-{slug}"


def set_system_password(username, password):
    run_command(["chpasswd"], input_text=f"{username}:{password}")
    LOGGER.info("Updated password for user %s", username)


def connect_wifi(ssid, wifi_password, connection_name):
    optional_command(["systemctl", "stop", "hostapd.service"])
    optional_command(["systemctl", "stop", "dnsmasq.service"])
    optional_command(["ip", "addr", "flush", "dev", WLAN_IF])
    optional_command(["ip", "link", "set", WLAN_IF, "up"])
    optional_command(["nmcli", "radio", "wifi", "on"])
    optional_command(["nmcli", "device", "set", WLAN_IF, "managed", "yes"])
    optional_command(["nmcli", "connection", "delete", connection_name])
    optional_command(["nmcli", "device", "wifi", "rescan", "ifname", WLAN_IF])

    run_command(
        [
            "nmcli",
            "connection",
            "add",
            "type",
            "wifi",
            "ifname",
            WLAN_IF,
            "con-name",
            connection_name,
            "ssid",
            ssid,
        ]
    )

    if wifi_password:
        run_command(
            [
                "nmcli",
                "connection",
                "modify",
                connection_name,
                "wifi-sec.key-mgmt",
                "wpa-psk",
                "wifi-sec.psk",
                wifi_password,
            ]
        )
    else:
        run_command(
            [
                "nmcli",
                "connection",
                "modify",
                connection_name,
                "wifi-sec.key-mgmt",
                "none",
            ]
        )

    run_command(
        [
            "nmcli",
            "connection",
            "modify",
            connection_name,
            "connection.autoconnect",
            "yes",
            "802-11-wireless.hidden",
            "no",
        ]
    )
    run_command(["nmcli", "connection", "up", connection_name])
    LOGGER.info("Connected to Wi-Fi SSID %s with connection %s", ssid, connection_name)


def switch_nginx_to_dashboard():
    if NGINX_ACTIVE_SNIPPET.exists() or NGINX_ACTIVE_SNIPPET.is_symlink():
        NGINX_ACTIVE_SNIPPET.unlink()
    NGINX_ACTIVE_SNIPPET.symlink_to(NGINX_DASHBOARD_SNIPPET)
    run_command(["systemctl", "reload", "nginx.service"])
    LOGGER.info("Switched nginx to dashboard mode")


def switch_nginx_to_onboarding():
    if NGINX_ACTIVE_SNIPPET.exists() or NGINX_ACTIVE_SNIPPET.is_symlink():
        NGINX_ACTIVE_SNIPPET.unlink()
    NGINX_ACTIVE_SNIPPET.symlink_to(NGINX_ONBOARDING_SNIPPET)
    optional_command(["systemctl", "reload", "nginx.service"])
    LOGGER.info("Switched nginx to onboarding mode")


def persist_metadata(admin_user, hostname, ssid, connection_name):
    ADMIN_USER_FILE.write_text(f"{admin_user}\n", encoding="utf-8")
    HOSTNAME_FILE.write_text(f"{hostname}\n", encoding="utf-8")
    SSID_FILE.write_text(f"{ssid}\n", encoding="utf-8")
    CONNECTION_FILE.write_text(f"{connection_name}\n", encoding="utf-8")
    INIT_FILE.write_text("initialized\n", encoding="utf-8")
    LOGGER.info("Wrote onboarding state files")


def restart_ap_mode():
    optional_command(["rfkill", "unblock", "wlan"])
    optional_command(["nmcli", "device", "set", WLAN_IF, "managed", "no"])
    optional_command(["ip", "link", "set", WLAN_IF, "down"])
    optional_command(["ip", "addr", "flush", "dev", WLAN_IF])
    optional_command(["ip", "link", "set", WLAN_IF, "up"])
    optional_command(["ip", "addr", "add", AP_CIDR, "dev", WLAN_IF])
    optional_command(["systemctl", "start", "hostapd.service"])
    optional_command(["systemctl", "start", "dnsmasq.service"])
    switch_nginx_to_onboarding()


def update_provisioning_state(status, message=""):
    with PROVISIONING_LOCK:
        PROVISIONING_STATE["status"] = status
        PROVISIONING_STATE["message"] = message


def read_provisioning_state():
    with PROVISIONING_LOCK:
        return dict(PROVISIONING_STATE)


def provision_device(payload, admin_user):
    connection_name = connection_name_for_ssid(payload["ssid"])

    try:
        # Give the HTTP response a chance to reach the browser before AP teardown.
        time.sleep(1.0)
        connect_wifi(payload["ssid"], payload["wifi_password"], connection_name)
        run_command(["hostnamectl", "set-hostname", payload["hostname"]])
        set_system_password(admin_user, payload["admin_password"])
        persist_metadata(admin_user, payload["hostname"], payload["ssid"], connection_name)
        switch_nginx_to_dashboard()
        update_provisioning_state(
            "success",
            "configuration completed; reconnect to the target Wi-Fi and open http://openclaw.local",
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        LOGGER.exception("Provisioning command failed")
        restart_ap_mode()
        update_provisioning_state("error", stderr or "system command failed during provisioning")
    except Exception as exc:
        LOGGER.exception("Unexpected provisioning failure")
        restart_ap_mode()
        update_provisioning_state("error", str(exc))


@APP.route("/")
def index():
    return send_file(SETUP_PAGE)


@APP.route("/api/status")
def status():
    admin_user = select_admin_user()
    provisioning_state = read_provisioning_state()
    return jsonify(
        {
            "initialized": INIT_FILE.exists(),
            "admin_user": admin_user,
            "hostname_default": "openclaw",
            "provisioning_status": provisioning_state["status"],
            "provisioning_message": provisioning_state["message"],
        }
    )


@APP.route("/setup", methods=["POST"])
def setup():
    admin_user = select_admin_user()
    try:
        payload = validate_payload(request.form)
        current_state = read_provisioning_state()
        if current_state["status"] == "running":
            return jsonify({"status": "error", "message": "configuration is already in progress"}), 409

        update_provisioning_state(
            "running",
            "configuration accepted; the device is switching to the target Wi-Fi",
        )
        Thread(
            target=provision_device,
            args=(payload, admin_user),
            daemon=True,
        ).start()
        return jsonify(
            {
                "status": "accepted",
                "message": "configuration accepted; reconnect to the target Wi-Fi when the hotspot disconnects",
                "hostname": payload["hostname"],
                "admin_user": admin_user,
            }
        ), 202
    except ValueError as exc:
        LOGGER.warning("Validation error: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        LOGGER.exception("Unexpected provisioning failure")
        return jsonify({"status": "error", "message": str(exc)}), 500


if __name__ == "__main__":
    APP.run(host="0.0.0.0", port=5000)
