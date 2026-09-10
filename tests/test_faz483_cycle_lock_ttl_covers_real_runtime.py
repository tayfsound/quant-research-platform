"""Faz 483 — kilit TTL'i görevin GERÇEK süresini kapsamalı.

Canlı olay (2026-09-10, kullanıcı: "sistem dondu resmen üç gündür"):
`ingest_order_book_task`ın `_CycleLock` TTL'i 120 sn'ydi ama görev canlıda
en uzun **631 sn** sürüyordu. Redis kilidi iş hâlâ devam ederken süresi
dolup AÇILIYOR, beat'in gönderdiği sonraki kopya onu "serbest" bulup
EŞZAMANLI ikinci (üçüncü, dördüncü...) bir kopya başlatıyordu — yani
kilit hiç kilitlemiyordu. Sonuç: Celery kuyruğunda 400 görev birikmiş,
saatte üretilen karar ~600'den ~50-100'e düşmüştü.

Bu tuzak Faz 207-sonrasında bir kez teşhis edilmişti ama SADECE beat
aralığı hizalanmıştı; TTL dokunulmadığı için görev yavaşladıkça
(watchlist 104->123 sembol + Faz 440'ın 5. HTTP çağrısı) aynı olay geri
geldi. Bu test iki değişmezi birlikte kilitliyor.
"""
import re

# Canlı log'dan ölçülen en uzun süreler (sn). Yeni bir görev yavaşlarsa
# burası da güncellenmeli — testin amacı tam olarak bu farkındalığı
# zorunlu kılmak.
_OBSERVED_MAX_RUNTIME = {
    # Faz 483-devam: ana döngü canlıda hiç TAMAMLANMADI (3 eşzamanlı kopya
    # birbirini kilitliyordu); süre sembol başına ölçülen ~13 sn x 123
    # sembol = ~2460 sn'den türetildi (Faz 484: duvar-saati 20 sn/sembol,
    # elapsed_s'in ölçtüğü propose süresine veri çekme de eklenince).
    "run_trading_cycle_task": 2460,
    "run_medium_term_cycle_task": 2460,
    "ingest_order_book_task": 631,
    "ingest_candles_task": 313,
    "close_due_shadow_positions_task": 302,
    "close_due_benched_shadow_positions_task": 179,
    "close_due_positions_task": 46,
    "refresh_market_state_cluster_task": 37,
    "refresh_open_position_pnl_summary_task": 27,
    "portfolio_stress_guardian_task": 22,
    "run_pairs_trading_task": 9,
}


def _lock_ttls() -> dict[str, int]:
    """services/tasks.py'deki `_CycleLock("lock:<task>", ttl_seconds=N)`
    çağrılarını okur. Kaynağı ayrıştırmak, her görevi tek tek çalıştırıp
    kilit davranışını taklit etmekten hem çok daha hızlı hem de bir
    görevin TTL'i sessizce düşürüldüğünde kesin olarak kırılıyor."""
    source = open("services/tasks.py").read()
    pairs = re.findall(
        r'_CycleLock\(\s*"lock:([a-z_]+)"\s*,\s*ttl_seconds=(\d+)\s*\)', source
    )
    assert pairs, "services/tasks.py'de hic _CycleLock bulunamadi"
    return {name: int(ttl) for name, ttl in pairs}


def test_every_lock_ttl_exceeds_the_observed_runtime_of_its_task():
    """TTL, gözlenen en uzun sürenin en az 1,5 katı olmalı — marj olmadan
    görev biraz yavaşladığında kilit yine iş sürerken açılır."""
    ttls = _lock_ttls()
    too_short = {}
    for task, runtime in _OBSERVED_MAX_RUNTIME.items():
        ttl = ttls.get(task)
        if ttl is None:
            continue  # bu görev _CycleLock kullanmıyor
        if ttl < runtime * 1.5:
            too_short[task] = (ttl, runtime)

    assert not too_short, (
        "kilit TTL'i gercek sureyi kapsamiyor -- kilit is surerken acilir ve "
        f"escanli kopyalar baslar: {too_short}"
    )


def test_order_book_ingestion_lock_specifically_covers_its_631_second_runtime():
    """Olayın merkezindeki görev için açık, isimli koruma."""
    ttl = _lock_ttls()["ingest_order_book_task"]
    assert ttl >= 631 * 1.5, f"TTL {ttl} sn, gozlenen 631 sn'lik sure icin yetersiz"


def test_beat_schedule_is_not_far_below_the_real_runtime():
    """Aralık gerçek süreden çok kısaysa (kilit doğru olsa bile) kuyruğa
    yalnızca kilide takılıp "skipped" dönen boş kopyalar birikir — Faz
    207-sonrasında 853, Faz 483'te 400 görevlik kuyruk tam bu yüzden
    oluştu.

    Eşik neden 1/4: boş kopyalar zararsız DEĞİL ama pahalı da değil
    (kilide takılıp ~0,01 sn'de dönüyorlar) — asıl zarar sayıları
    büyüdüğünde ortaya çıkıyor. Gerçek kusur 120 sn'lik aralığa karşı
    1600 sn'lik döngüydü: tamamlanma başına ~13 boş kopya. Öte yandan
    aralığı gerçek sürenin ta üstüne çekmek de yanlış olur — döngü
    bittikten sonra bir sonrakinin başlaması gereksizce gecikir. 1/4,
    "en fazla ~4 boş kopya" demek: taşmayı yakalar, hızlı yeniden
    başlamayı engellemez. (İlk hâli 1/2'ydi; run_trading_cycle_task'ın
    600 sn'lik aralığını 800 sn'ye çıkarmayı gerektiriyordu ve bu, boş
    kopya sayısını 2,7'den 2'ye düşürmek için döngüler arası boşluğu
    uzatmak olurdu — ölçülen bir faydası yok.)"""
    from services.celery_app import celery_app

    schedules: dict[str, float] = {}
    for entry in celery_app.conf.beat_schedule.values():
        task = entry["task"]
        schedule = entry["schedule"]
        if isinstance(schedule, int | float):
            schedules[task] = min(schedules.get(task, float("inf")), float(schedule))

    too_frequent = {
        task: (schedules[task], runtime)
        for task, runtime in _OBSERVED_MAX_RUNTIME.items()
        if task in schedules and schedules[task] < runtime / 4
    }

    assert not too_frequent, (
        "beat araligi gercek sureye gore cok sik -- kuyruga bos kopya birikir: "
        f"{too_frequent}"
    )
