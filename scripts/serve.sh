#!/usr/bin/env bash
# AI 趋势日报 · 固定地址预览（本机 + 局域网 / 手机）
#
#   本机：  http://localhost:8080/index.html
#   局域网：http://<Mac 主机名>.local:8080/index.html   ← 手机用这个，IP 变了也能用
#           http://<局域网 IP>:8080/index.html          ← 备用
#
# 服务直接读磁盘，每天 build_site.py 覆盖文件后无需重启，地址永久不变。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

HOST="$(hostname | sed 's/\.local$//')"
LAN_IP="$(ipconfig getifaddr en0 || ipconfig getifaddr en1 || echo '未连接 Wi-Fi')"

if lsof -ti tcp:8080 >/dev/null 2>&1; then
  echo "服务已在运行（端口 8080）"
else
  echo "启动中：python3 -m http.server 8080 --bind 0.0.0.0"
  (nohup python3 -m http.server 8080 --bind 0.0.0.0 >/tmp/ai-daily-digest-server.log 2>&1 &)
  sleep 1
fi

echo
echo "  本机      http://localhost:8080/index.html"
echo "  手机/局域网  http://${HOST}.local:8080/index.html"
echo "  备用 IP    http://${LAN_IP}:8080/index.html"
echo

# 生成二维码方便手机扫码
QR="$ROOT/deploy/qrcode-lan.png"
curl -sS -o "$QR" \
  "https://api.qrserver.com/v1/create-qr-code/?size=480x480&margin=16&data=http%3A%2F%2F${HOST}.local%3A8080%2Findex.html" \
  && echo "二维码已更新：$QR" || echo "（二维码生成失败，请手动在手机输入上面的地址）"

open "http://localhost:8080/index.html"
echo "已用系统默认浏览器打开：http://localhost:8080/index.html"
