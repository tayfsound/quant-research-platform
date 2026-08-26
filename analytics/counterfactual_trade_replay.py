"""Karşı-Olgusal İşlem Replay'i — Faz 363.

analytics/agent_ablation.py'nin leave-one-out ölçümü, bir ajanın oyu
silinince council'in NİHAİ İNANCININ (belief-fusion) değişip
değişmediğini söylüyor ("flipped_direction" — yön değişti ama hâlâ
yönlü). Ama gerçekleşen işlemin PNL'ini bu karşı-olgusal senaryoya
atfetmek yanlış olurdu: o senaryoda TAMAMEN FARKLI bir işlem (ters
yön, farklı giriş/stop/hedef) açılırdı. Bu modül, o karşı-olgusal
işlemin GERÇEK tarihsel fiyat verisiyle ne yapacağını bar-bar
simüle eder — services/position_closer.py'nin GERÇEK, canlıda
kullanılan çıkış/breakeven mantığının SAF (DB'siz) bir yansıması.

Kasıtlı olarak SADECE ölçüm — hiçbir ajanın canlı oy hakkını burada
otomatik değiştirmiyor (analytics/agent_ablation.py ile aynı ilke).

Bar-bar yürüyüş her adımda SADECE bar KAPANIŞINI kullanıyor (yüksek/
düşük'e bakıp "içeride tetiklendi" varsaymıyor) — çünkü GERÇEK canlı
sistem de pozisyonları periyodik (services/position_closer.py'nin
celery task'ı, ~60sn'de bir) en son KAPANIŞ fiyatıyla tarıyor, barın
içindeki anlık en iyi/en kötü anı hiç görmüyor. Bu, backtest'in canlı
sistemden DAHA İYİ görünmesini sağlayacak (gerçekte imkansız) bir
"gözetleme" avantajı vermemek için bilinçli bir seçim."""
from dataclasses import dataclass


def check_exit(
    direction: str, current_price: float, stop_loss_price: float | None, take_profit_price: float | None,
) -> str | None:
    """services/position_closer.py::PositionCloser._exit_reason ile
    BİREBİR AYNI mantık (kopyalandı, DB/self bağımlılığı olmadan saf
    bir fonksiyona indirgendi)."""
    if direction == "LONG":
        if stop_loss_price is not None and current_price <= stop_loss_price:
            return "stop_loss"
        if take_profit_price is not None and current_price >= take_profit_price:
            return "take_profit"
    elif direction == "SHORT":
        if stop_loss_price is not None and current_price >= stop_loss_price:
            return "stop_loss"
        if take_profit_price is not None and current_price <= take_profit_price:
            return "take_profit"
    return None


@dataclass(frozen=True)
class BreakevenSettings:
    """services/position_closer.py::_load_breakeven_trigger_r_multiple/
    _load_trailing_stop_distance_pct/_load_progressive_lock_* ile AYNI
    ayarlar — gatherer katmanı bunları BİR KEZ (bar başına değil, tüm
    replay için) AppSettings'ten okuyup buraya taşır. pump_fade_v1'e
    özel dal (sabit yüzdelik eşikler) BİLEREK dahil değil — bu modül
    SADECE AI konseyi kararlarının karşı-olgusallarını (onchain_agent
    gibi council ajanları) simüle ediyor, pump_fade_v1 hiç council
    oylaması kullanmıyor zaten (bkz. services/pump_fade_strategy.py)."""
    trigger_r_multiple: float
    trailing_pct: float
    progressive_lock_min_profit_r: float
    progressive_lock_fraction: float


def compute_ratcheted_stop(
    direction: str,
    entry_price: float,
    stop_loss_price: float,
    original_stop_loss_price: float | None,
    current_price: float,
    settings: BreakevenSettings,
) -> float:
    """services/position_closer.py::PositionCloser._apply_breakeven_stop
    ile AYNI mantık (SADECE pump_fade_v1 DIŞI dal — yukarıdaki
    BreakevenSettings notuna bkz.), DB okuma/yazma olmadan saf bir
    fonksiyona indirgendi. SADECE sıkılaştırır, asla gevşetmez."""
    if direction == "LONG":
        original_risk = entry_price - stop_loss_price
        candidates = [stop_loss_price]
        if original_risk > 0 and current_price >= entry_price + original_risk * settings.trigger_r_multiple:
            candidates.append(entry_price)
        if original_stop_loss_price is not None and original_stop_loss_price < entry_price:
            true_original_risk = entry_price - original_stop_loss_price
            profit_r = (current_price - entry_price) / true_original_risk
            if profit_r >= settings.progressive_lock_min_profit_r:
                candidates.append(
                    entry_price + true_original_risk * profit_r * settings.progressive_lock_fraction
                )
        if settings.trailing_pct > 0:
            trailing_candidate = current_price - entry_price * settings.trailing_pct
            if trailing_candidate > entry_price:
                candidates.append(trailing_candidate)
        return max(candidates)

    original_risk = stop_loss_price - entry_price
    candidates = [stop_loss_price]
    if original_risk > 0 and current_price <= entry_price - original_risk * settings.trigger_r_multiple:
        candidates.append(entry_price)
    if original_stop_loss_price is not None and original_stop_loss_price > entry_price:
        true_original_risk = original_stop_loss_price - entry_price
        profit_r = (entry_price - current_price) / true_original_risk
        if profit_r >= settings.progressive_lock_min_profit_r:
            candidates.append(
                entry_price - true_original_risk * profit_r * settings.progressive_lock_fraction
            )
    if settings.trailing_pct > 0:
        trailing_candidate = current_price + entry_price * settings.trailing_pct
        if trailing_candidate < entry_price:
            candidates.append(trailing_candidate)
    return min(candidates)


# Faz 344/362 gibi gerçek pozisyonların ("basis_arb_max_hold",
# "belief_reversal_exit" vb.) aksine, karşı-olgusal bir işlemin canlıda
# hiç bir "azami tutma süresi" ayarı yok — bu yüzden makul, sabit bir
# üst sınır: gerçek RiskTargetStage hedefleri genelde saatler-günler
# mertebesinde vadeleniyor (bkz. mae_mfe.py'nin kendi ATR-tabanlı
# hedef ufku), 14 gün bunun için cömert bir üst sınır.
MAX_REPLAY_BARS = 14 * 24 * 60  # 14 gün, 1 dakikalık barlarla


def walk_price_path_to_exit(
    bars: list,
    direction: str,
    entry_price: float,
    initial_stop_price: float,
    take_profit_price: float,
    breakeven_settings: BreakevenSettings,
    original_stop_price: float | None = None,
) -> dict:
    """bars: zaman sırasına göre (eskiden yeniye) GERÇEK OHLCV barları
    (opened_at'tan SONRA). Her bar kapanışında önce çıkış kontrolü
    (check_exit), sonra (çıkış yoksa) breakeven/trailing ratchet
    uygulanır — services/position_closer.py'nin canlı döngüsüyle AYNI
    sıra. Hiçbir çıkış tetiklenmezse (MAX_REPLAY_BARS'a kadar) dürüstçe
    exit_reason=None döner — icat edilmiş bir çıkış asla üretilmez."""
    stop_price = initial_stop_price
    for i, bar in enumerate(bars[:MAX_REPLAY_BARS]):
        reason = check_exit(direction, bar.close, stop_price, take_profit_price)
        if reason is not None:
            return {"exit_price": bar.close, "exit_reason": reason, "exit_bar_index": i, "final_stop_price": stop_price}
        stop_price = compute_ratcheted_stop(
            direction, entry_price, stop_price, original_stop_price, bar.close, breakeven_settings,
        )
    return {"exit_price": None, "exit_reason": None, "exit_bar_index": None, "final_stop_price": stop_price}
