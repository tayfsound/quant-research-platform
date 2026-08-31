#!/bin/bash
# Faz 334 — kullanıcı isteği: bu ortamda (yerel geliştirme) uvicorn/celery'yi
# hiçbir process supervisor izlemiyordu — kod hatası değil, operasyonel bir
# boşluk. Gerçek olay: close_due_positions_task saatlerce çalışmayan
# pencerelere sahipti (son 3 günde 17+ tane 30dk-6.5 saatlik boşluk),
# bir pozisyon (ZROUSDT) stop seviyesini geçtikten 30 SAAT SONRA kapandı.
# Bu script, gerçek production'daki K8s liveness/readiness probe'unun (Faz
# 180'de zaten kurulup test edildi) yerel geliştirme karşılığı: uvicorn +
# celery worker_default'u periyodik kontrol edip düşerse otomatik yeniden
# başlatır.
#
# Kullanım: nohup ./scripts/service_watchdog.sh > /tmp/service_watchdog_stdout.log 2>&1 &
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="/tmp/service_watchdog.log"
CHECK_INTERVAL_SECONDS=60

log() {
    echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') $1" >> "$LOG_FILE"
}

is_uvicorn_alive() {
    pgrep -f "uvicorn api.main:app" > /dev/null 2>&1
}

is_celery_default_alive() {
    # Faz 389 — gerçek olay: worker_default'un ANA (master) süreci
    # kaybolup çocukları PPID=1'e (init) yetim kaldığı bir durumda, bu
    # kontrol SADECE `pgrep -f` ile TÜM eşleşen süreçleri (yetimler
    # DAHİL) buluyordu — yetim çocuklar da AYNI komut satırıyla eşleştiği
    # için watchdog "worker zaten sağlıklı" sanıp 3+ saat hiç yeniden
    # başlatmadı, hiçbir yeni görev işlenmedi. Artık SADECE bu watchdog
    # script'inin (`$$`) DOĞRUDAN çocuğu olan bir eşleşme "sağlıklı"
    # sayılıyor — start_celery_default()'ın `nohup ... &` ile başlattığı
    # gerçek master'ın PPID'i her zaman $$ olur, yetim çocuklarınki 1.
    pgrep -f "celery -A services.celery_app worker -Q celery --loglevel=info -n worker_default" -P $$ > /dev/null 2>&1
}

# Faz 360 — kullanıcı isteği: pozisyon kapatmada kaymayı azaltmak için
# gerçek-zamanlı WebSocket izleyici (services/realtime_position_monitor.py).
# REST periyodik tarama (close_due_positions_task) hâlâ arkadaki güvenlik
# ağı olarak çalışıyor — bu süreç sadece kapanışı hızlandırıyor, WS koparsa
# sistem güvenliği REST'e geri düşüyor. Kalıcı bir asyncio event loop'u
# gerektirdiği için Celery'nin prefork worker modeline uymuyor, ayrı bir
# süreç olarak izleniyor.
is_realtime_monitor_alive() {
    pgrep -f "services.realtime_position_monitor" > /dev/null 2>&1
}

# Faz 365 — backlog #49 (kullanıcı isteği: "veri toplayıp ölçebiliyorsak
# iyi, en önemli kısım orası"). Binance'in ücretsiz !forceOrder@arr
# akışını dinleyip liquidation_events'e yazan, AYNI kalıcı-süreç
# gerekçesiyle (asyncio event loop, Celery prefork'a uymuyor)
# realtime_position_monitor ile birebir aynı desende izlenen süreç.
is_liquidation_listener_alive() {
    pgrep -f "services.binance_liquidation_listener" > /dev/null 2>&1
}

is_health_ok() {
    [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health 2>/dev/null)" = "200" ]
}

start_uvicorn() {
    log "uvicorn DOWN (ya da /health yanıt vermiyor) -- yeniden başlatılıyor"
    cd "$REPO_DIR" || return
    nohup .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn_watchdog.log 2>&1 &
    disown
}

start_celery_default() {
    log "celery worker_default DOWN -- yeniden başlatılıyor"
    # Faz 389 — is_celery_default_alive artık yetimleri "ölü" sayıyor,
    # ama onları burada da temizlemezsek eski master'ın bıraktığı
    # sonlandırılmamış çocuklar süresiz birikip kaynak tüketmeye devam
    # eder (yeni master onları hiç bilmez/yönetmez).
    pkill -f "celery -A services.celery_app worker -Q celery --loglevel=info -n worker_default" 2>/dev/null
    cd "$REPO_DIR" || return
    nohup .venv/bin/celery -A services.celery_app worker -Q celery --loglevel=info -n worker_default@%h > /tmp/celery_default_watchdog.log 2>&1 &
    disown
}

start_realtime_monitor() {
    log "realtime_position_monitor DOWN -- yeniden başlatılıyor"
    cd "$REPO_DIR" || return
    nohup .venv/bin/python -m services.realtime_position_monitor > /tmp/realtime_position_monitor_watchdog.log 2>&1 &
    disown
}

start_liquidation_listener() {
    log "binance_liquidation_listener DOWN -- yeniden başlatılıyor"
    cd "$REPO_DIR" || return
    nohup .venv/bin/python -m services.binance_liquidation_listener > /tmp/liquidation_listener_watchdog.log 2>&1 &
    disown
}

log "watchdog başladı (kontrol aralığı: ${CHECK_INTERVAL_SECONDS}sn, repo: ${REPO_DIR})"

while true; do
    if ! is_uvicorn_alive || ! is_health_ok; then
        start_uvicorn
    fi
    if ! is_celery_default_alive; then
        start_celery_default
    fi
    if ! is_realtime_monitor_alive; then
        start_realtime_monitor
    fi
    if ! is_liquidation_listener_alive; then
        start_liquidation_listener
    fi
    sleep "$CHECK_INTERVAL_SECONDS"
done
