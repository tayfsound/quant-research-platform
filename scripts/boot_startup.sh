#!/bin/bash
# Faz 474 — kullanıcı isteği (backlog #9): makine yeniden başladığında
# HİÇBİR ŞEY otomatik ayağa kalkmıyordu.
#
# GERÇEK OLAY (2026-09-08): kullanıcı "AI pozisyon almıyor" dedi. Makine
# ~3 saat önce yeniden başlamış ve hiçbir servis gelmemişti — Docker
# Desktop kapalı (dolayısıyla postgres/redis yok), watchdog yok
# (dolayısıyla uvicorn/celery worker/realtime_position_monitor/
# liquidation_listener yok), celery beat yok. Sistem 3 saat boyunca
# tamamen sessiz durdu, HİÇBİR alarm yok — /tmp de reboot'ta silindiği
# için watchdog logu bile boştu ("log boş" ≠ "sorun yok").
#
# Bu script o kurtarma sırasını otomatikleştiriyor. Kurulum:
#   ./scripts/install_boot_startup.sh
# Kaldırma:
#   launchctl unload ~/Library/LaunchAgents/com.quantresearch.boot.plist
#   rm ~/Library/LaunchAgents/com.quantresearch.boot.plist
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$HOME/Library/Logs/quant_boot_startup.log"
# /tmp DEĞİL: reboot'ta silindiği için tam da teşhis etmek istediğimiz
# olayın kaydı kayboluyordu.
mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') $1" >> "$LOG_FILE"; }

wait_for() {  # wait_for <saniye> <açıklama> <komut...>
    local timeout=$1 label=$2; shift 2
    local waited=0
    until "$@" >/dev/null 2>&1; do
        if [ "$waited" -ge "$timeout" ]; then
            log "ZAMAN AŞIMI (${timeout}sn): $label"
            return 1
        fi
        sleep 5
        waited=$((waited + 5))
    done
    log "hazır: $label (${waited}sn)"
    return 0
}

log "=== boot startup başladı (repo: $REPO_DIR) ==="

# 1) Docker Desktop — GUI uygulaması, kendiliğinden açılmıyor.
if ! docker ps >/dev/null 2>&1; then
    log "Docker daemon yok — Docker Desktop açılıyor"
    open -a Docker 2>>"$LOG_FILE"
fi
wait_for 300 "docker daemon" docker ps || { log "Docker gelmedi, DURULDU"; exit 1; }

# 2) Konteynerler de otomatik başlamıyor.
cd "$REPO_DIR" || { log "repo dizinine girilemedi"; exit 1; }
docker compose up -d postgres redis >>"$LOG_FILE" 2>&1
wait_for 180 "postgres" docker exec quant-research-platform-postgres-1 pg_isready -U quant \
    || { log "postgres gelmedi, DURULDU"; exit 1; }

# 3) Watchdog — uvicorn + celery worker + realtime_position_monitor +
#    liquidation_listener'ı 60sn içinde ayağa kaldırır.
if ! pgrep -f "scripts/service_watchdog.sh" >/dev/null 2>&1; then
    log "watchdog başlatılıyor"
    nohup "$REPO_DIR/scripts/service_watchdog.sh" > /tmp/service_watchdog_stdout.log 2>&1 &
    disown
else
    log "watchdog zaten çalışıyor"
fi

# 4) KRİTİK: celery beat'i watchdog YÖNETMİYOR. Beat olmadan worker
#    ayakta olsa bile HİÇBİR trading döngüsü tetiklenmez — sistem
#    "çalışıyor" görünür ama hiç karar üretmez. 2026-09-08'de tam
#    olarak bu oldu.
if ! pgrep -f "celery -A services.celery_app beat" >/dev/null 2>&1; then
    log "celery beat başlatılıyor"
    nohup "$REPO_DIR/.venv/bin/celery" -A services.celery_app beat --loglevel=info \
        > /tmp/celery_beat_boot.log 2>&1 &
    disown
else
    log "celery beat zaten çalışıyor"
fi

# 5) Doğrulama — "başlattım" demek yetmez, GERÇEKTEN geldi mi.
wait_for 180 "uvicorn /health" \
    bash -c '[ "$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)" = "200" ]' \
    || log "UYARI: /health 200 dönmedi (watchdog denemeye devam edecek)"

log "=== boot startup bitti ==="
