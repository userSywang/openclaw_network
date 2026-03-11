#!/bin/bash
set -euo pipefail

INIT_FILE="/etc/openclaw/initialized"
WLAN_IF="wlan0"
AP_CIDR="192.168.4.1/24"
HOSTAPD_CONF="/etc/hostapd/hostapd.conf"
LOG_TAG="openclaw-firstboot"

log() {
    logger -t "$LOG_TAG" "$1"
    echo "$1"
}

update_ssid() {
    local mac_suffix
    local new_ssid
    local tmp_file

    mac_suffix="$(tr -d ':' < "/sys/class/net/${WLAN_IF}/address" 2>/dev/null | tail -c 5 || true)"
    if [ -z "${mac_suffix}" ]; then
        mac_suffix="0000"
    fi

    new_ssid="OpenClaw-${mac_suffix^^}"
    tmp_file="$(mktemp)"
    sed "s/^ssid=.*/ssid=${new_ssid}/" "$HOSTAPD_CONF" > "$tmp_file"
    install -m 600 "$tmp_file" "$HOSTAPD_CONF"
    rm -f "$tmp_file"
    log "Updated AP SSID to ${new_ssid}"
}

configure_ap_address() {
    rfkill unblock wlan || true
    nmcli device set "$WLAN_IF" managed no || true
    ip link set "$WLAN_IF" down || true
    ip addr flush dev "$WLAN_IF" || true
    ip link set "$WLAN_IF" up
    ip addr add "$AP_CIDR" dev "$WLAN_IF"
    log "Configured ${WLAN_IF} with ${AP_CIDR}"
}

main() {
    if [ -f "$INIT_FILE" ]; then
        log "Initialization marker exists; skipping onboarding mode"
        exit 0
    fi

    if ! ip link show "$WLAN_IF" >/dev/null 2>&1; then
        log "Wireless interface ${WLAN_IF} not found"
        exit 1
    fi

    mkdir -p /etc/openclaw /var/log/openclaw

    update_ssid
    configure_ap_address

    systemctl start hostapd.service
    log "Started hostapd"

    systemctl start dnsmasq.service
    log "Started dnsmasq"

    systemctl start --no-block openclaw-onboarding.service
    log "Queued onboarding service startup"
}

main "$@"
