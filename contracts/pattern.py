"""Pattern Recognition Domain Contracts — Wyckoff/Elliott/market structure."""
from datetime import datetime

from pydantic import BaseModel, Field


class PatternContext(BaseModel):
    """PatternAgent için yapısal/pattern bağlamı."""
    structure_phase: str = "neutral"       # "accumulation", "distribution", "markup", "markdown", "neutral" (Wyckoff)
    break_of_structure: str = "none"       # "bullish", "bearish", "none" (BOS)
    change_of_character: bool = False      # CHoCH — trend değişim uyarısı
    fair_value_gap: str = "none"           # "bullish", "bearish", "none" (FVG)
    swing_structure: str = "mixed"         # "higher_highs_higher_lows", "lower_highs_lower_lows", "mixed"
    liquidity_sweep: str = "none"          # "buy_side_swept", "sell_side_swept", "none"
    # Faz 223: klasik Fibonacci retracement — en son swing high/low
    # arasında en yakın seviye ("23.6%".."78.6%" veya "none") ve fiyatın o
    # seviyeye göre konumu ("at_support"/"at_resistance"/"none").
    fibonacci_nearest_level: str = "none"
    fibonacci_price_position: str = "none"
    # Faz 237: kullanıcı isteği — "gerçek Wyckoff analizi yaptıralım."
    # Kesin tanımlı, ayrık Wyckoff olayları — structure_phase'in (yukarıda)
    # kasıtlı olarak kaba genel-rejim yaklaşıklamasından farklı olarak.
    # "spring", "upthrust", "sign_of_strength", "sign_of_weakness", "none".
    wyckoff_event: str = "none"
    # Faz 268-sonrası — kullanıcı bulgusu: "fiyatın akümüle olduğu
    # bölgeler" (Volume Profile) hiç yoktu — swing high/low tabanlı
    # destek/direnç dışında gerçek bir hacim-fiyat analizi olmadan
    # teknik analiz eksik kalıyordu. bkz. signal_engine.compute_
    # volume_profile — tick verisi olmadığı için her bar'ın hacmi kendi
    # [low,high] aralığına dağıtılan, dürüst bir yaklaşıklama.
    poc_distance_pct: float = 0.0          # fiyatın POC'a göre uzaklığı (+üstünde, -altında)
    in_value_area: bool = False            # fiyat hacmin ~%70'inin işlem gördüğü aralıkta mı
    near_high_volume_node: bool = False    # fiyat bilinen bir yüksek-hacim (birikim) bölgesine yakın mı
    timestamp: datetime = Field(default_factory=datetime.now)
