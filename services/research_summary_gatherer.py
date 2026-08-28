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
    # Faz 363 — backlog #15, kullanıcı isteği: "kâr edip zarara dönen
    # pozisyonların ne kadarı stop yanlış yerleştirildiği için, ne kadarı
    # gerçek yön hatası" + "bu kaybın toplam zarardaki payı % olarak
    # dashboard'a kart olarak eklenmeli (SL/likidasyon/breakeven kırılımı)."
    ("loss_breakdown", "Zarar Kırılımı (SL/Likidasyon/Breakeven)", "loss-breakdown", "services.loss_breakdown_gatherer", "gather_loss_breakdown"),
    # Backlog #14 (2026-08-26) — kullanıcı örneği: "BTC LONG'da 100
    # pozisyon, 15'i stop olmuş, 13'ü yön hatası, 2'si stop süpürülüp
    # sonra hedefe gitmiş." loss_breakdown'ın (yukarıda) TEK genel toplamı
    # yerine sembol×yön kırılımı — AYNI sınıflandırma, farklı kesim.
    ("symbol_direction_loss_breakdown", "Zarar Kırılımı — Sembol × Yön", "symbol-direction-loss-breakdown", "services.symbol_direction_loss_breakdown_gatherer", "gather_symbol_direction_loss_breakdown"),
    # Faz 364-devam — kullanıcı sorusu: "hangi ajan hangi rejimde isabetli,
    # ölçmezsek bilemeyiz, belki şu an zayıf görünen bir ajan başka bir
    # rejimde hayat kurtarıyordur." strategy_regime_compatibility'nin AYNI
    # saf fonksiyonu, etiket "strateji" yerine "ajan domain'i" ile.
    ("agent_domain_regime_reliability", "Ajan Güvenilirliği — Rejime Göre", "agent-domain-regime-reliability", "services.agent_domain_regime_reliability_gatherer", "gather_agent_domain_regime_reliability"),
    # Faz 364-devam — kullanıcı hipotezi: bir rejimde SHORT başarısızsa,
    # aynı rejimde LONG başarılı mı — sistematik bir ters ilişki var mı?
    ("direction_regime_asymmetry", "Yön × Rejim Asimetrisi", "direction-regime-asymmetry", "services.direction_regime_asymmetry_gatherer", "gather_direction_regime_asymmetry"),
    # Faz 364-devam — kullanıcı isteği: Feature IC ölçümleri rejime göre
    # kırılmalı, "hangi rejimde hangi sinyal işe yarıyor" sorusu.
    ("feature_ic_by_regime", "Feature IC × Rejim", "feature-ic-by-regime", "services.feature_ic_by_regime_gatherer", "gather_feature_ic_by_regime"),
    # Faz 368 — Feature Intelligence Layer Faz A. Gerçek veriyle doğrulandı:
    # trend/ema_alignment/momentum/vwap_confirm/adx_strong_confirm
    # birbirleriyle r=1.000 — council'e 5 ayrı oy gibi giriyorlar ama
    # matematiksel olarak TEK bir sinyalin 5 farklı ismi. Bu modül bu
    # çakışmayı (redundancy matrisi) ve koşullu IC'yi (b bilinirken a'nın
    # kattığı EK bilgi) ölçüyor.
    ("feature_relationship", "Feature Relationship", "feature-relationship", "services.feature_relationship_gatherer", "gather_feature_relationship"),
    # Faz 368-devam — GPT'nin "Agent Interaction & Incremental Information
    # Layer" önerisi. agent_ablation'ın tek-domain leave-one-out'unun
    # ötesine geçip, aynı kararda birlikte oy veren HER ajan çiftinin
    # (A+B ikisi birden çıkınca ne olur) nedensel ilişkisini ölçüyor.
    ("agent_pairwise_ablation", "Agent Interaction", "agent-pairwise-ablation", "services.agent_pairwise_ablation_gatherer", "gather_agent_pairwise_ablation"),
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
