"""Research Summary — Faz 326. Kullanıcı isteği: "araştırma" (Grup B,
ölçüm-only) modüllerini tek tek görüntülemek yerine tek bir düğmeyle
hepsinin özetini alabilmek — detaylar yine kendi sayfalarında kalıyor,
sadece HIZLI bir genel bakış katmanı ekleniyor.

10 modülün hepsi AYNI mimariyi paylaşıyor (services/*_gatherer.py::
gather_*() — her çağrıda gerçek alt sistemlerden taze hesaplar, hiçbir
şey önceden saklanmıyor). Kullanıcı kararıyla: özet de AYNI şekilde
CANLI hesaplanıyor (stale/eski bir anlık görüntü değil) — bazı modüller
(ör. tp_sl_confluence tüm watchlist'i tarıyor) birkaç saniye sürebiliyor,
bu yüzden 10'u SIRAYLA değil ThreadPoolExecutor ile PARALEL çalıştırılıyor
— toplam süre en yavaş TEK modülün süresine yakın kalıyor, 10'unun
toplamına değil."""
from concurrent.futures import ThreadPoolExecutor, as_completed

# (modül anahtarı, etiket, dashboard "view" anahtarı, gather fonksiyonunun import yolu)
_MODULES = [
    ("self_model", "Self-Model", "self-model", "services.self_model_gatherer", "gather_self_reliability_snapshot"),
    ("causal_inference", "Causal Inference", "causal-inference", "services.causal_inference_gatherer", "gather_causal_relationships"),
    ("collective_intelligence", "Collective Intelligence", "collective-intelligence", "services.collective_intelligence_gatherer", "gather_collective_intelligence"),
    ("mae_mfe_confidence", "MAE/MFE Güven Aralığı", "mae-mfe-confidence", "services.mae_mfe_confidence_gatherer", "gather_mae_mfe_confidence"),
    ("meta_learning_effectiveness", "Meta-Learning Effectiveness", "meta-learning-effectiveness", "services.meta_learning_effectiveness_gatherer", "gather_meta_learning_effectiveness"),
    ("market_world_model", "Risk Simülatörü", "market-world-model", "services.market_world_model_gatherer", "gather_market_world_model"),
    ("direction_prediction_v2", "Direction Prediction v2", "direction-prediction-v2", "services.direction_prediction_v2_gatherer", "gather_direction_prediction_v2"),
    ("opportunity_quality", "Opportunity Quality", "opportunity-quality", "services.opportunity_quality_gatherer", "gather_opportunity_quality"),
    ("agent_ablation", "Agent Ablation", "agent-ablation", "services.agent_ablation_gatherer", "gather_agent_ablation"),
    ("tp_sl_confluence", "TP/SL Confluence", "tp-sl-confluence", "services.tp_sl_confluence_gatherer", "gather_tp_sl_confluence"),
    ("agent_combination_reliability", "Ajan Kombinasyonu Güvenilirliği", "agent-combination-reliability", "services.agent_combination_reliability_gatherer", "gather_agent_combination_reliability"),
    ("strategy_regime_compatibility", "Strateji × Rejim Uyumu", "strategy-regime-compatibility", "services.strategy_regime_compatibility_gatherer", "gather_strategy_regime_compatibility"),
    ("strategy_hypothesis_scanner", "Strateji Hipotez Tarayıcı", "strategy-hypothesis-scanner", "services.strategy_hypothesis_scanner_gatherer", "gather_strategy_hypothesis_candidates"),
    # Faz 356 — kullanıcı isteği: "2-3 gündür kazanma oranım düştü, sistem
    # bunu kendi kendine fark edebilsin mi." "scientific-self-correction"
    # view'ı için henüz ayrı bir detay sayfası yok (dedicated page bu
    # turun kapsamı dışında bırakıldı) — "Detaya git" şimdilik boş içerik
    # gösterir, kart özeti yine de canlı ve doğru.
    ("scientific_self_correction", "Bilimsel Öz-Düzeltme", "scientific-self-correction", "services.scientific_self_correction_gatherer", "gather_scientific_self_correction"),
    # Faz 362 — kullanıcı isteği: "sinyal tutarlılığı" eşiğinin (girişten
    # önce kaç ardışık cycle aynı yönde olmalı) optimum değeri veri
    # büyüdükçe değişebilir — sabit bir sayı yerine, her çağrıda TAZE
    # yeniden hesaplanan bir gözlem katmanı. Canlı gate ayrı bir ayarla
    # (signal_persistence_min_consistent_cycles) çalışıyor, bu panel
    # SADECE "şu an veriye göre optimum ne olurdu" sorusuna cevap veriyor
    # — otomatik uygulanmıyor, kullanıcı isterse elle günceller.
    ("signal_persistence", "Sinyal Tutarlılığı Eşiği", "signal-persistence", "services.signal_persistence_gatherer", "gather_signal_persistence_analysis"),
]


def _run_one(key: str, label: str, view: str, module_path: str, func_name: str) -> dict:
    import importlib

    entry = {"key": key, "label": label, "view": view, "result": None, "error": None}
    try:
        mod = importlib.import_module(module_path)
        func = getattr(mod, func_name)
        entry["result"] = func()
    except Exception as exc:
        # Faz 326 — bir modülün hatası (ör. dış API zaman aşımı) diğer 9'unu
        # engellememeli — fail-closed, sessiz değil: hata mesajı açıkça
        # dönüyor, frontend o kartı "geçici olarak alınamadı" gösterebilir.
        entry["error"] = str(exc)
    return entry


def gather_research_summary() -> dict:
    """10 Grup B modülünün hepsini PARALEL, canlı olarak çalıştırıp tek
    bir listede döner — modül sırası sabit (_MODULES ile aynı), her
    zaman TÜM 10 kayıt var (başarısız olan bile "error" alanıyla)."""
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=len(_MODULES)) as executor:
        futures = {
            executor.submit(_run_one, key, label, view, module_path, func_name): key
            for key, label, view, module_path, func_name in _MODULES
        }
        for future in as_completed(futures):
            entry = future.result()
            results[entry["key"]] = entry

    # Sıra _MODULES ile AYNI (as_completed tamamlanma sırasına göre değil).
    ordered = [results[key] for key, *_ in _MODULES]
    return {"modules": ordered}
