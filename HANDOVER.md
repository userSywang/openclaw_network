# OpenClaw Network 交接文档

## 1. 项目目标

本项目用于 Armbian 设备无外设首次配网：

- 首次启动自动开启热点 `OpenClaw-XXXX`
- 设备固定地址 `192.168.4.1`
- 用户用手机连接热点并打开 `http://192.168.4.1`
- 提交主机名、管理员密码、目标 Wi-Fi 信息
- 设备退出配网模式，接入目标 Wi-Fi
- 后续通过 `http://openclaw.local` 访问 OpenClaw dashboard

## 2. 当前实现状态

当前已完成并验证通过的能力：

- 首次启动进入 AP 模式
- `wlan0` 配置为 `192.168.4.1/24`
- `hostapd + dnsmasq + Flask + nginx + avahi + systemd + NetworkManager` 架构跑通
- 手机可访问 `http://192.168.4.1`
- 提交 Wi-Fi 后设备成功连接目标网络
- 写入 `/etc/openclaw/initialized`
- 初始化后停止 `hostapd` / `dnsmasq`
- 重启后不再回到热点模式
- `openclaw.local` 可访问最小 dashboard
- dashboard 可显示当前 Wi-Fi 信息
- 支持恢复出厂后重新进入配网模式

## 3. 仓库内关键文件

- `install.sh`：安装依赖、复制配置、启用服务、执行静态校验
- `firstboot.sh`：首次启动控制 AP 模式
- `onboarding.py`：配网页面后端、Wi-Fi 切换、状态写入
- `setup.html`：手机端 onboarding 页面
- `dashboard.py`：最小 dashboard 和 `/api/status`
- `factory-reset.sh`：恢复出厂
- `openclaw-firstboot.service`
- `openclaw-onboarding.service`
- `openclaw-dashboard.service`
- `nginx-openclaw.conf`
- `avahi-openclaw.service`

## 4. 当前用户侧实际流程

1. 设备首次开机后出现热点 `OpenClaw-XXXX`
2. 手机连接热点，密码默认 `openclaw123`
3. 手机打开 `http://192.168.4.1`
4. 页面填写：
   - 设备主机名
   - 管理员密码
   - 目标 Wi-Fi SSID
   - 目标 Wi-Fi 密码
5. 提交后页面会提示：
   - 如果设备已连接目标 Wi-Fi，点击“执行下一步”
6. 手机切回目标 Wi-Fi 后，点击按钮访问 `http://openclaw.local`
7. 进入 OpenClaw dashboard

## 5. 当前已确认的设备行为

在已验证设备上，以下结果已确认：

- `openclaw-firstboot` 在未初始化时运行，初始化后因条件不满足而跳过
- `hostapd` / `dnsmasq` 仅在配网模式运行
- `openclaw-dashboard.service` 在初始化完成后正常运行
- `wlan0` 成功建立 `openclaw-client-*` 连接
- `/etc/openclaw/initialized`、`wifi_ssid`、`device_hostname`、`nm_connection_name` 等文件正常生成
- `openclaw.local` 已能打开 dashboard

## 6. 需要注意的设计事实

- 当前管理员账户固定为 `root`
- 前端文案已改为“固定管理员账户 root”
- 当前不支持修改 Linux 用户名，只支持设置管理员密码
- “执行下一步”按钮本质是访问 `http://openclaw.local`
- 它不是跨网络自动跳转，前提是手机已切回目标 Wi-Fi

## 7. 新机部署步骤

```bash
git clone https://github.com/userSywang/openclaw_network.git
cd openclaw_network
git checkout main
sudo bash install.sh
sudo reboot
```

## 8. 新机验收步骤

1. 验证热点是否出现  
   预期：能看到 `OpenClaw-XXXX`
2. 验证 onboarding 页面  
   预期：`http://192.168.4.1` 可打开
3. 提交 Wi-Fi 配置  
   预期：页面出现“执行下一步”
4. 手机切回目标 Wi-Fi 并点击按钮  
   预期：打开 `http://openclaw.local`
5. 重启后复验  
   预期：不再起热点，dashboard 仍可访问
6. 恢复出厂复验

```bash
sudo /opt/openclaw/factory-reset.sh
sudo reboot
```

预期：重新回到热点配网模式

## 9. 推荐现场检查命令

```bash
systemctl status openclaw-firstboot --no-pager
systemctl status openclaw-onboarding --no-pager
systemctl status openclaw-dashboard --no-pager
systemctl status hostapd --no-pager
systemctl status dnsmasq --no-pager
systemctl status nginx --no-pager
systemctl status avahi-daemon --no-pager
nmcli connection show
ls -l /etc/openclaw
curl -I http://127.0.0.1:8080
curl http://127.0.0.1:8080/api/status
curl -I http://openclaw.local
```

## 10. 当前已知未做的优化

- 未实现“已初始化但无网时自动重新进入 AP”
- 未实现可修改管理员用户名
- `openclaw.local` 依赖 mDNS，局域网环境异常时应准备 IP 或 `<hostname>.local` 作为备用入口
- dashboard 目前是最小实现，后续可接入正式业务 API 和页面

## 11. 建议后续工作

- 增加“无有效 uplink 时自动回退 AP”能力
- 给 dashboard 增加设备状态、网络状态、API 状态展示
- 补充备用访问入口提示
- 若业务需要，再设计独立管理员账户而不是复用 `root`
