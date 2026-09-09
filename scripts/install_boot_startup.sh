#!/bin/bash
# Faz 474 — boot_startup.sh'i macOS LaunchAgent olarak kurar.
#
# LaunchAgent (LaunchDaemon DEĞİL) bilinçli seçim: boot_startup.sh Docker
# DESKTOP'ı açıyor (`open -a Docker`) ve bu bir GUI uygulaması — kullanıcı
# oturumu bağlamı gerekiyor. LaunchDaemon oturum öncesi çalışır ve
# `open -a` orada çalışmaz.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_PATH="$HOME/Library/LaunchAgents/com.quantresearch.boot.plist"

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.quantresearch.boot</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${REPO_DIR}/scripts/boot_startup.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <!-- KeepAlive YOK: bu tek seferlik bir kurtarma script'i, kalıcı bir
         servis değil. Sürekli çalışması gereken izleme işini
         service_watchdog.sh yapıyor. KeepAlive verilseydi launchd
         script'i bitince tekrar tekrar çalıştırırdı. -->
    <key>StandardOutPath</key>
    <string>${HOME}/Library/Logs/quant_boot_launchd.log</string>
    <key>StandardErrorPath</key>
    <string>${HOME}/Library/Logs/quant_boot_launchd.log</string>
</dict>
</plist>
PLIST

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo "Kuruldu: $PLIST_PATH"
echo "Log:     ~/Library/Logs/quant_boot_startup.log"
echo
echo "Kaldirmak icin:"
echo "  launchctl unload $PLIST_PATH && rm $PLIST_PATH"
