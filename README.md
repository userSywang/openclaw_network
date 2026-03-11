# OpenClaw 配网系统

这是一个面向 Armbian 的首次启动配网最小实现，保留现有架构：

- `hostapd` 提供首次启动热点
- `dnsmasq` 提供 DHCP/DNS 劫持到 `192.168.4.1`
- `Flask` 提供首次配网页面
- `nginx` 对外统一暴露 HTTP 入口
- `avahi-daemon` 广播 HTTP 服务
- `systemd` 编排启动顺序
- `NetworkManager` 负责连接用户 Wi-Fi

## 工作流程

1. 首次启动且 `/etc/openclaw/initialized` 不存在时，`openclaw-firstboot.service` 进入配网模式。
2. 设备把 `wlan0` 配置为 `192.168.4.1/24`，然后启动 `hostapd` 和 `dnsmasq`。
3. 用户连接热点 `OpenClaw-XXXX`，访问 `http://192.168.4.1`。
4. Flask 页面提交主机名、系统管理员密码、Wi-Fi SSID 和密码。
5. `onboarding.py` 先停止 `hostapd` 和 `dnsmasq`，再用 `nmcli` 连接用户 Wi-Fi。
6. 连接成功后：
   - 设置系统管理员密码
   - 设置主机名
   - 写入 `/etc/openclaw/initialized`
   - 将 nginx 切换到 dashboard 代理配置
7. 后续通过 `http://openclaw.local` 访问；如果你修改了主机名，则使用 `http://<hostname>.local`。

## 仓库文件

- `install.sh`
- `firstboot.sh`
- `onboarding.py`
- `setup.html`
- `hostapd.conf`
- `hostapd-default`
- `dnsmasq-openclaw.conf`
- `avahi-openclaw.service`
- `nginx-openclaw.conf`
- `nginx-snippets/openclaw-onboarding.conf`
- `nginx-snippets/openclaw-dashboard.conf`
- `openclaw-firstboot.service`
- `openclaw-onboarding.service`
- `factory-reset.sh`

## 安装

```bash
cd /path/to/openclaw_network
sudo bash install.sh
sudo reboot
```

安装脚本会：

- 安装 `hostapd`、`dnsmasq`、`nginx`、`avahi-daemon`、`python3-flask`、`network-manager`、`qrencode`
- 复制所有配置和脚本到系统目录
- 将 nginx 默认切到 onboarding 模式
- 执行静态配置校验：
  - `nginx -t`
  - `dnsmasq --test`
  - `hostapd -t /etc/hostapd/hostapd.conf`
  - `systemd-analyze verify ...`
- 仅启用：
  - `openclaw-firstboot`
  - `nginx`
  - `avahi-daemon`
  - `NetworkManager`

注意：安装脚本不会直接 `enable hostapd` 或 `enable dnsmasq`，这两个服务只在首次配网流程中由 `firstboot.sh` 控制。

## 目标路径

- `/opt/openclaw/firstboot.sh`
- `/opt/openclaw/onboarding.py`
- `/opt/openclaw/factory-reset.sh`
- `/opt/openclaw/templates/setup.html`
- `/etc/openclaw/initialized`
- `/etc/openclaw/admin_user`
- `/etc/openclaw/device_hostname`
- `/etc/openclaw/wifi_ssid`
- `/etc/openclaw/nm_connection_name`
- `/etc/hostapd/hostapd.conf`
- `/etc/default/hostapd`
- `/etc/dnsmasq.d/openclaw.conf`
- `/etc/avahi/services/openclaw.service`
- `/etc/nginx/sites-available/openclaw`
- `/etc/nginx/snippets/openclaw-onboarding.conf`
- `/etc/nginx/snippets/openclaw-dashboard.conf`
- `/etc/nginx/snippets/openclaw-active-location.conf`
- `/etc/systemd/system/openclaw-firstboot.service`
- `/etc/systemd/system/openclaw-onboarding.service`

## 自检

以下校验应在目标 Armbian 设备上执行：

```bash
systemctl status openclaw-firstboot
systemctl status openclaw-onboarding
systemctl status hostapd
systemctl status dnsmasq
systemctl status nginx
systemctl status avahi-daemon

ip addr show wlan0
cat /etc/hostapd/hostapd.conf
journalctl -u openclaw-firstboot -n 50
journalctl -u openclaw-onboarding -n 50
curl -I http://192.168.4.1
curl -I http://openclaw.local
```

## 恢复出厂

```bash
sudo /opt/openclaw/factory-reset.sh
```

恢复脚本会：

- 删除 OpenClaw 初始化标志和 OpenClaw 保存的连接元数据
- 仅删除 OpenClaw 创建的 `NetworkManager` 连接
- 将 nginx 恢复到 onboarding 代理
- 重新触发首次配网服务

注意：恢复出厂不会自动把系统管理员密码回滚到某个默认值。下一次完成 onboarding 时，用户可以重新设置密码。
