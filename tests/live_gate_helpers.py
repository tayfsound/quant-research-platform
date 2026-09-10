"""Faz 482 — kapı (gate) testleri için ortak yardımcı.

`services/decision_recorder.py`'deki 10 post-hoc kapı artık SADECE gerçek
borsaya giden (live/testnet) sembollerde ENGELLİYOR; simüle sembollerde ya
da trading_mode="test" iken kapı yine değerlendiriliyor ama pozisyonu
engellemiyor (`gate_bypassed_test_mode` olarak kaydediliyor) — kullanıcı
isteği: "sadece live modu için geçerli olacak kapılar bunlar, test moduna
engel olmaması lazımdı."

`execution_mode` global ayarının varsayılanı "simulated" olduğu için,
haritada açıkça yer almayan HER sembol simüledir. Dolayısıyla "bu kapı
canlıda gerçekten engelliyor mu" sorusunu test eden her testin, sembolünü
açıkça gerçek-borsa olarak işaretlemesi gerekiyor — aşağıdaki context
manager bunu yapıp sonunda ayarı eski hâline getiriyor (paylaşılan
quantdb_test'te kalıcı iz bırakmıyor).
"""
import json
from contextlib import contextmanager

from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory


@contextmanager
def global_real_exchange_mode(mode: str = "live"):
    """Tüm sembolleri (haritada açıkça yer almayanlar dahil) gerçek borsaya
    yönlendirir. Dosyanın TAMAMI canlı-mod kapı davranışını test ediyorsa
    her teste tek tek `symbol_on_real_exchange` yazmak yerine autouse bir
    fixture olarak kullanılır. Blok bitince eski global değer (ya da
    ayarın hiç olmaması durumu) geri yüklenir."""
    with SessionFactory.get_session() as session:
        before = AppSettingsRepository(session).get("execution_mode")
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("execution_mode", mode, updated_by="test")
    try:
        yield
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set(
                "execution_mode", before if before is not None else "simulated",
                updated_by="test",
            )


@contextmanager
def symbol_on_real_exchange(symbol: str, mode: str = "live"):
    """`symbol`'ü execution_mode_symbols haritasında `mode` olarak işaretler
    (varsayılan "live"), blok bitince haritayı eski hâline döndürür.

    NEDEN "testnet" DEĞİL: `DecisionRecorder.record()` çözümlenen mod
    TAM OLARAK "testnet" olduğunda GERÇEK bir Binance testnet emri
    denemesi yapıyor (doğrulandı: testler "Margin is insufficient"
    hatasıyla düşüyordu). "live" ise o dala hiç girmiyor (execution_mode
    "simulated"a düşüyor, hiçbir ağ çağrısı yok) ama `_routes_to_real_
    exchange` için "simüle değil" sayılıyor — testin ölçmek istediği şey
    tam olarak bu."""
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        raw = repo.get("execution_mode_symbols")
        before = json.loads(raw) if raw else {}
        current = dict(before)
        current[symbol] = mode
        repo.set("execution_mode_symbols", json.dumps(current), updated_by="test")
    try:
        yield symbol
    finally:
        with SessionFactory.get_session() as session:
            repo = AppSettingsRepository(session)
            raw = repo.get("execution_mode_symbols")
            current = json.loads(raw) if raw else {}
            if symbol in before:
                current[symbol] = before[symbol]
            else:
                current.pop(symbol, None)
            repo.set("execution_mode_symbols", json.dumps(current), updated_by="test")
