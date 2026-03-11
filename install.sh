#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/opt/openclaw"
TEMPLATE_DIR="${INSTALL_DIR}/templates"
CONFIG_DIR="/etc/openclaw"
NGINX_SITE="/etc/nginx/sites-available/openclaw"
NGINX_SNIPPET_DIR="/etc/nginx/snippets"
ACTIVE_SNIPPET="${NGINX_SNIPPET_DIR}/openclaw-active-location.conf"
SYSTEMD_DIR="/etc/systemd/system"

validate_hostapd_config() {
    local conf="/etc/hostapd/hostapd.conf"
    local required_keys=(
        interface
        driver
        ssid
        hw_mode
        channel
        wpa
        wpa_passphrase
        wpa_key_mgmt
        rsn_pairwise
    )
    local key

    for key in "${required_keys[@]}"; do
        if ! grep -q "^${key}=" "$conf"; then
            echo "hostapd config validation failed: missing ${key} in ${conf}" >&2
            return 1
        fi
    done

    echo "hostapd config sanity check passed."
}

echo "=== OpenClaw 配网系统安装脚本 ==="

echo "[1/9] 安装软件包..."
apt-get update
apt-get install -y hostapd dnsmasq nginx avahi-daemon python3-flask python3-pip network-manager qrencode

echo "[2/9] 创建目录..."
mkdir -p "$INSTALL_DIR" "$TEMPLATE_DIR" "$CONFIG_DIR" /var/log/openclaw "$NGINX_SNIPPET_DIR"

echo "[3/9] 复制应用文件..."
install -m 755 "${REPO_DIR}/firstboot.sh" "${INSTALL_DIR}/firstboot.sh"
install -m 755 "${REPO_DIR}/onboarding.py" "${INSTALL_DIR}/onboarding.py"
install -m 755 "${REPO_DIR}/factory-reset.sh" "${INSTALL_DIR}/factory-reset.sh"
install -m 644 "${REPO_DIR}/setup.html" "${TEMPLATE_DIR}/setup.html"

echo "[4/9] 复制网络与服务配置..."
install -m 600 "${REPO_DIR}/hostapd.conf" /etc/hostapd/hostapd.conf
install -m 644 "${REPO_DIR}/hostapd-default" /etc/default/hostapd
install -m 644 "${REPO_DIR}/dnsmasq-openclaw.conf" /etc/dnsmasq.d/openclaw.conf
install -m 644 "${REPO_DIR}/avahi-openclaw.service" /etc/avahi/services/openclaw.service
install -m 644 "${REPO_DIR}/nginx-openclaw.conf" "$NGINX_SITE"
install -m 644 "${REPO_DIR}/nginx-snippets/openclaw-onboarding.conf" "${NGINX_SNIPPET_DIR}/openclaw-onboarding.conf"
install -m 644 "${REPO_DIR}/nginx-snippets/openclaw-dashboard.conf" "${NGINX_SNIPPET_DIR}/openclaw-dashboard.conf"
ln -sfn "${NGINX_SNIPPET_DIR}/openclaw-onboarding.conf" "$ACTIVE_SNIPPET"

echo "[5/9] 复制 systemd 单元..."
install -m 644 "${REPO_DIR}/openclaw-firstboot.service" "${SYSTEMD_DIR}/openclaw-firstboot.service"
install -m 644 "${REPO_DIR}/openclaw-onboarding.service" "${SYSTEMD_DIR}/openclaw-onboarding.service"
systemctl unmask hostapd.service || true
systemctl disable hostapd.service dnsmasq.service || true
systemctl daemon-reload

echo "[6/9] 配置 nginx 站点..."
ln -sfn "$NGINX_SITE" /etc/nginx/sites-enabled/openclaw
rm -f /etc/nginx/sites-enabled/default

echo "[7/9] 生成二维码..."
qrencode -o "${INSTALL_DIR}/qrcode.png" "http://192.168.4.1"

echo "[8/9] 执行静态配置校验..."
nginx -t
dnsmasq --test
validate_hostapd_config
systemd-analyze verify \
    "${SYSTEMD_DIR}/openclaw-firstboot.service" \
    "${SYSTEMD_DIR}/openclaw-onboarding.service"

echo "[9/9] 启用服务..."
systemctl enable openclaw-firstboot.service
systemctl enable nginx.service
systemctl enable avahi-daemon.service
systemctl enable NetworkManager.service
systemctl restart nginx.service

echo
echo "=== 安装完成 ==="
echo "首次启动后，设备会在未初始化状态下进入 AP 配网模式。"
