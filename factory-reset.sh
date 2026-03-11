#!/bin/bash
set -euo pipefail

CONFIG_DIR="/etc/openclaw"
INIT_FILE="${CONFIG_DIR}/initialized"
ADMIN_USER_FILE="${CONFIG_DIR}/admin_user"
HOSTNAME_FILE="${CONFIG_DIR}/device_hostname"
SSID_FILE="${CONFIG_DIR}/wifi_ssid"
CONNECTION_FILE="${CONFIG_DIR}/nm_connection_name"
ONBOARDING_SNIPPET="/etc/nginx/snippets/openclaw-onboarding.conf"
ACTIVE_SNIPPET="/etc/nginx/snippets/openclaw-active-location.conf"
LOG_TAG="openclaw-reset"

log() {
    logger -t "$LOG_TAG" "$1"
    echo "$1"
}

restore_nginx() {
    if [ -L "$ACTIVE_SNIPPET" ] || [ -e "$ACTIVE_SNIPPET" ]; then
        rm -f "$ACTIVE_SNIPPET"
    fi
    ln -s "$ONBOARDING_SNIPPET" "$ACTIVE_SNIPPET"
    nginx -t
    systemctl reload nginx.service
}

main() {
    local connection_name=""
    local answer=""

    echo "This will reset OpenClaw onboarding state and remove only the Wi-Fi connection created by OpenClaw."
    read -r -p "Continue? [y/N] " answer
    if [[ ! "$answer" =~ ^[Yy]$ ]]; then
        log "Reset cancelled"
        exit 0
    fi

    if [ -f "$CONNECTION_FILE" ]; then
        connection_name="$(tr -d '\r\n' < "$CONNECTION_FILE")"
    fi

    systemctl stop openclaw-onboarding.service || true
    systemctl stop hostapd.service || true
    systemctl stop dnsmasq.service || true
    nmcli device set wlan0 managed yes || true

    if [ -n "$connection_name" ]; then
        nmcli connection delete "$connection_name" || true
        log "Deleted NetworkManager connection ${connection_name}"
    fi

    rm -f \
        "$INIT_FILE" \
        "$ADMIN_USER_FILE" \
        "$HOSTNAME_FILE" \
        "$SSID_FILE" \
        "$CONNECTION_FILE"
    log "Removed OpenClaw state files"

    restore_nginx
    log "Restored nginx onboarding config"

    systemctl restart openclaw-firstboot.service
    log "Restarted firstboot service"
}

main "$@"
