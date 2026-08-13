"""Feature Registry — Faz 294 (Cognitive Core 2.0 / M1) Feature lineage
ve veri bilimi çekirdeği.

ctx.market.features (services/orchestrator.py::build_cognitive_context)
şu ana kadar hangi feature'ın NEREDEN geldiğini yalnızca kod okuyarak
(grep) bulabileceğiniz düz bir dict'ti. Bu modül GERÇEK, elle doğrulanmış
bir katalog — her feature'ın hangi fonksiyon/modülden geldiğini, tipini
ve ne anlama geldiğini programatik olarak sorgulanabilir kılıyor.

Faz 269'daki system_events gibi bu da mevcut hesaplamaların YERİNE
geçmiyor — onların ÜZERİNE bir keşfedilebilirlik/dokümantasyon katmanı
ekliyor. Kayıtlar market_data/features/signal_engine.py, services/
orchestrator.py ve market_data/onchain/onchain_provider.py'nin GERÇEK
kaynak kodundan elle doğrulanarak çıkarıldı (2026-08-13) — icat edilmiş
bir feature listesi değil.

Yeni bir feature eklendiğinde bu registry'nin GÜNCELLENMESİ gerekiyor —
otomatik senkronize olmuyor (statik bir katalog, kod introspection'ı
değil); tests/test_feature_registry.py bilinen bir örnek kümesini
doğruluyor, tam kapsamı değil."""
from dataclasses import dataclass

ValueType = str  # "float" | "str" | "bool"


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    source_module: str
    source_function: str
    value_type: ValueType
    description: str


_SPECS = [
    # --- market_data.features.signal_engine::compute_technical_signals ---
    FeatureSpec("RSI", "market_data.features.signal_engine", "compute_technical_signals", "float",
                "Relative Strength Index (standart 14 periyot)"),
    FeatureSpec("ema", "market_data.features.signal_engine", "compute_technical_signals", "float",
                "hızlı EMA (trend hesabındaki kısa bacak)"),
    FeatureSpec("macd", "market_data.features.signal_engine", "compute_technical_signals", "float",
                "MACD çizgisi (fast EMA - slow EMA)"),
    FeatureSpec("trend", "market_data.features.signal_engine", "compute_technical_signals", "str",
                "bullish/bearish/neutral — ema20 vs ema50"),
    FeatureSpec("momentum", "market_data.features.signal_engine", "compute_technical_signals", "str",
                "strengthening/weakening/neutral — MACD histogram eğilimi"),
    FeatureSpec("market_structure", "market_data.features.signal_engine", "compute_technical_signals", "str",
                "swing high/low karşılaştırmasına dayalı piyasa yapısı"),
    FeatureSpec("ema_alignment", "market_data.features.signal_engine", "compute_technical_signals", "str",
                "bullish_aligned/bearish_aligned/mixed — kısa/orta/uzun EMA sıralaması"),
    FeatureSpec("volatility_regime", "market_data.features.signal_engine", "compute_technical_signals", "str",
                "son gerçekleşen volatilitenin kendi geçmiş dağılımına göre konumu"),
    FeatureSpec("volume_confirmation", "market_data.features.signal_engine", "compute_technical_signals", "bool",
                "son hacim, 20 barlık rolling ortalamanın üzerinde mi"),
    FeatureSpec("atr", "market_data.features.signal_engine", "compute_technical_signals", "float",
                "Average True Range (14 periyot)"),
    FeatureSpec("bollinger_percent_b", "market_data.features.signal_engine", "compute_technical_signals", "float",
                "fiyatın Bollinger bantları arasındaki konumu (0=alt, 1=üst)"),
    FeatureSpec("bollinger_bandwidth", "market_data.features.signal_engine", "compute_technical_signals", "float",
                "Bollinger bant genişliğinin SMA'ya göre oranı (düşük=sıkışma)"),
    FeatureSpec("vwap_deviation_pct", "market_data.features.signal_engine", "compute_technical_signals", "float",
                "fiyatın pencere-VWAP'ına göre göreli sapması (%)"),
    FeatureSpec("adx", "market_data.features.signal_engine", "compute_technical_signals", "float",
                "Average Directional Index (14 periyot, trend gücü)"),
    FeatureSpec("di_plus", "market_data.features.signal_engine", "compute_technical_signals", "float",
                "ADX'in +DI bileşeni"),
    FeatureSpec("di_minus", "market_data.features.signal_engine", "compute_technical_signals", "float",
                "ADX'in -DI bileşeni"),
    FeatureSpec("obv_trend", "market_data.features.signal_engine", "compute_technical_signals", "str",
                "On-Balance Volume trendi"),
    FeatureSpec("price_obv_divergence", "market_data.features.signal_engine", "compute_technical_signals", "str",
                "fiyat ile OBV arasındaki uyumsuzluk"),
    # --- market_data.features.signal_engine::compute_pattern_signals ---
    FeatureSpec("structure_phase", "market_data.features.signal_engine", "compute_pattern_signals", "str",
                "basitleştirilmiş Wyckoff faz yaklaşıklaması (sofistike bir Wyckoff analizi değil)"),
    FeatureSpec("break_of_structure", "market_data.features.signal_engine", "compute_pattern_signals", "str",
                "fiyat en son önemli swing high/low'u aştı mı"),
    FeatureSpec("change_of_character", "market_data.features.signal_engine", "compute_pattern_signals", "bool",
                "piyasa yapısı son swing setlerinde yön değiştirdi mi"),
    FeatureSpec("fair_value_gap", "market_data.features.signal_engine", "compute_pattern_signals", "str",
                "3-mumluk ICT Fair Value Gap tanımı"),
    FeatureSpec("swing_structure", "market_data.features.signal_engine", "compute_pattern_signals", "str",
                "swing high/low dizisine dayalı yapı"),
    FeatureSpec("liquidity_sweep", "market_data.features.signal_engine", "compute_pattern_signals", "str",
                "son mum bir swing'in ötesine fitil atıp içeri kapandı mı"),
    FeatureSpec("fibonacci_nearest_level", "market_data.features.signal_engine", "compute_pattern_signals", "str",
                "fiyata en yakın Fibonacci geri çekilme seviyesi"),
    FeatureSpec("fibonacci_price_position", "market_data.features.signal_engine", "compute_pattern_signals", "str",
                "fiyatın Fibonacci seviyeleri arasındaki konumu"),
    FeatureSpec("wyckoff_event", "market_data.features.signal_engine", "compute_pattern_signals", "str",
                "tespit edilen Wyckoff olayı (varsa)"),
    # --- market_data.features.signal_engine::compute_quant_signals ---
    FeatureSpec("zscore", "market_data.features.signal_engine", "compute_quant_signals", "float",
                "fiyatın 20-barlık ortalamaya göre standart sapma cinsinden sapması"),
    FeatureSpec("realized_vol_percentile", "market_data.features.signal_engine", "compute_quant_signals", "float",
                "gerçekleşen volatilitenin kendi geçmiş dağılımındaki yüzdelik konumu"),
    FeatureSpec("autocorrelation", "market_data.features.signal_engine", "compute_quant_signals", "float",
                "getirilerin bir-gecikmeli otokorelasyonu"),
    FeatureSpec("hurst_exponent", "market_data.features.signal_engine", "compute_quant_signals", "float",
                "Hurst üsteli (>0.5 trend, <0.5 mean-reversion, ~0.5 rastgele yürüyüş)"),
    FeatureSpec("long_term_trend_regime", "market_data.features.signal_engine", "compute_quant_signals", "str",
                "uzun-vadeli trend rejimi sınıflandırması"),
    FeatureSpec("regime_changepoint_detected", "market_data.features.signal_engine", "compute_quant_signals", "bool",
                "rejim değişim noktası (changepoint) tespit edildi mi"),
    # --- services.orchestrator::build_cognitive_context doğrudan eklemeleri ---
    FeatureSpec("data_quality_score", "market_data.features.signal_engine", "compute_data_quality_score", "float",
                "fiyat spike/wick manipülasyonu (kötü print) şüphesi — 1.0=temiz"),
    FeatureSpec("high_impact_event_imminent", "market_data.macro.economic_calendar", "compute_event_proximity", "bool",
                "FOMC/CPI gibi yüksek etkili bir makro yayın HIGH_IMPACT_WINDOW_HOURS içinde mi"),
    FeatureSpec("daily_atr_pct", "market_data.features.signal_engine", "compute_daily_atr_pct", "float",
                "risk (stop/target) ölçeklendirmesi için sinyal zaman diliminden bağımsız günlük ATR yüzdesi"),
    FeatureSpec("mvrv_zscore", "market_data.onchain.onchain_provider", "fetch_mvrv_zscore", "float",
                "on-chain MVRV z-score (piyasa değeri / gerçekleşen değer)"),
    FeatureSpec("network_activity_trend", "market_data.onchain.onchain_provider", "fetch_network_activity_trend", "str",
                "on-chain ağ aktivite trendi"),
    FeatureSpec("hash_rate_trend", "market_data.onchain.onchain_provider", "fetch_hash_rate_trend", "str",
                "on-chain hash rate trendi"),
]

FEATURE_REGISTRY: dict[str, FeatureSpec] = {spec.name: spec for spec in _SPECS}


def get_feature_spec(name: str) -> FeatureSpec | None:
    return FEATURE_REGISTRY.get(name)


def list_features_by_source(source_function: str) -> list[FeatureSpec]:
    return [s for s in FEATURE_REGISTRY.values() if s.source_function == source_function]
