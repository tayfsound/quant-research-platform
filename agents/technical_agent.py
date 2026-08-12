"""Technical Agent — yapısal teknik analiz uzmanı."""
from dataclasses import dataclass

from contracts.agent import AgentDomain, AgentOpinion
from contracts.technical import TechnicalContext


@dataclass(frozen=True)
class TechnicalAgentCoefficients:
    """Faz 239-241 (CMA-ES online meta-learning) — TechnicalAgent'ın
    skorlama katsayıları artık kod içine gömülü sabitler değil, dışarıdan
    verilebilen (ve dolayısıyla CMA-ES ile ayarlanabilen) bir vektör.
    Varsayılan değerler AŞAĞIDAKİ mevcut sabitlerin BİREBİR aynısı — bu
    refactor tek başına hiçbir davranış değişikliği yapmaz, sadece
    katsayıları parametrize eder. Gerçek ayar/onay akışı
    meta_optimizer/agent_tuner.py + services/meta_learning_scheduler.py'de."""
    trend_weight: float = 1.0
    momentum_weight: float = 1.0
    market_structure_weight: float = 1.5
    ema_alignment_weight: float = 0.5
    rsi_extreme_weight: float = 1.0
    volume_confirmation_penalty: float = 0.3
    bollinger_confirm_weight: float = 0.5
    vwap_confirm_weight: float = 0.3
    adx_weak_discount: float = 0.7
    adx_strong_confirm_weight: float = 0.4
    obv_divergence_weight: float = 0.3
    confidence_divisor: float = 5.0

    def as_vector(self) -> list[float]:
        return [
            self.trend_weight, self.momentum_weight, self.market_structure_weight,
            self.ema_alignment_weight, self.rsi_extreme_weight, self.volume_confirmation_penalty,
            self.bollinger_confirm_weight, self.vwap_confirm_weight, self.adx_weak_discount,
            self.adx_strong_confirm_weight, self.obv_divergence_weight, self.confidence_divisor,
        ]

    @classmethod
    def field_names(cls) -> list[str]:
        return [
            "trend_weight", "momentum_weight", "market_structure_weight",
            "ema_alignment_weight", "rsi_extreme_weight", "volume_confirmation_penalty",
            "bollinger_confirm_weight", "vwap_confirm_weight", "adx_weak_discount",
            "adx_strong_confirm_weight", "obv_divergence_weight", "confidence_divisor",
        ]

    @classmethod
    def from_vector(cls, vector: list[float]) -> "TechnicalAgentCoefficients":
        return cls(**dict(zip(cls.field_names(), vector, strict=True)))


class TechnicalAgent:
    def __init__(self, coefficients: TechnicalAgentCoefficients | None = None):
        self.agent_id = "technical_agent_v1"
        self.coeffs = coefficients or TechnicalAgentCoefficients()

    def get_tunable_params(self) -> TechnicalAgentCoefficients:
        return self.coeffs

    def analyze(self, context: TechnicalContext) -> AgentOpinion:
        c = self.coeffs
        evidence = []
        caveats = []
        score = 0.0

        # Trend
        if context.trend == "bullish":
            score += c.trend_weight
            evidence.append("Market in bullish trend")
        elif context.trend == "bearish":
            score -= c.trend_weight
            evidence.append("Market in bearish trend")

        # Momentum
        if context.momentum == "strengthening" and context.trend == "bullish":
            score += c.momentum_weight
            evidence.append("Bullish momentum strengthening")
        elif context.momentum == "weakening" and context.trend == "bearish":
            score -= c.momentum_weight
            evidence.append("Bearish momentum strengthening")

        # Piyasa yapısı
        if context.market_structure == "higher_highs":
            score += c.market_structure_weight
            evidence.append("Higher highs structure — bullish continuation pattern")
        elif context.market_structure == "lower_lows":
            score -= c.market_structure_weight
            evidence.append("Lower lows structure — bearish continuation pattern")
        elif context.market_structure == "ranging":
            caveats.append("Market in consolidation — breakout needed for conviction")

        # EMA dizilimi
        if context.ema_alignment == "bullish_aligned":
            score += c.ema_alignment_weight
            evidence.append("EMAs bullishly aligned")
        elif context.ema_alignment == "bearish_aligned":
            score -= c.ema_alignment_weight
            evidence.append("EMAs bearishly aligned")

        # RSI aşırı bölgeler
        if context.rsi_value < 25:
            score += c.rsi_extreme_weight
            evidence.append(f"RSI extremely oversold ({context.rsi_value})")
        elif context.rsi_value > 75:
            score -= c.rsi_extreme_weight
            evidence.append(f"RSI extremely overbought ({context.rsi_value})")

        # Hacim teyidi
        # Faz 258: kritik bulgu — feature importance analiziyle (561 gerçek
        # kapanmış işlem üzerinden) ölçüldü: volume_confirmation=True iken
        # kazanma oranı %15.4, False iken %28.5 — yani "son mum, 20 mumluk
        # ortalamanın üstünde hacim" sağlıklı trend teyidinden çok, kısa
        # vadeli tükeniş/dönüş anını yakalıyor gibi görünüyor. Önceki kod
        # bunu +0.5 ile ödüllendiriyordu (bullish teyidi sayıyordu) —
        # gerçek veri tam tersini gösteriyor. Artık ölçülen yöne göre
        # (hafif, diğer daha güçlü sinyallerden — RSI ±1.0 gibi — küçük
        # kalacak şekilde) kalibre edildi; icat edilmiş bir katsayı değil,
        # gerçek geriye dönük ölçümün işaretiyle aynı yönde.
        if context.volume_confirmation:
            score -= c.volume_confirmation_penalty
            caveats.append(
                "Recent volume spike (above 20-bar average) — historically correlated with "
                "worse outcomes in this system (potential exhaustion/reversal, not confirmed continuation)"
            )
        else:
            caveats.append("Volume not confirming trend — potential divergence")

        # Volatilite
        if context.volatility_regime == "high":
            caveats.append("High volatility regime — reduced position sizing recommended")

        # Faz 237: Bollinger Bands — bandın DIŞINA taşmak (percent_b<0 ya da
        # >1) genelde ya gerçek bir kırılım ya da aşırı-uzama/dönüş adayı;
        # burada "mean-reversion" yorumuyla DEĞİL, mevcut trend'i DOĞRULAYAN
        # yönde kullanılıyor (trend güçlüyken bandın dışına taşmak devam
        # sinyali — trend yokken aşırı bölge yorumu QuantAgent'ın zaten
        # kapsadığı z-score'la çakışırdı).
        if context.bollinger_percent_b > 1.0 and context.trend == "bullish":
            score += c.bollinger_confirm_weight
            evidence.append(f"Price above upper Bollinger Band ({context.bollinger_percent_b:.2f}) confirming bullish trend")
        elif context.bollinger_percent_b < 0.0 and context.trend == "bearish":
            score -= c.bollinger_confirm_weight
            evidence.append(f"Price below lower Bollinger Band ({context.bollinger_percent_b:.2f}) confirming bearish trend")

        # Faz 237: VWAP sapması — fiyat "adil değerin" ne kadar üstünde/
        # altında, mevcut trend'i doğrulayan yönde hafif bir kanıt.
        if context.vwap_deviation_pct > 0.01 and context.trend == "bullish":
            score += c.vwap_confirm_weight
            evidence.append(f"Price {context.vwap_deviation_pct:.2%} above VWAP — real buying pressure")
        elif context.vwap_deviation_pct < -0.01 and context.trend == "bearish":
            score -= c.vwap_confirm_weight
            evidence.append(f"Price {context.vwap_deviation_pct:.2%} below VWAP — real selling pressure")

        # Faz 237: ADX — trend YÖNÜ değil GÜCÜ. Zayıf/yatay trend'te (ADX<20)
        # bu ajanın kendi trend/momentum sinyallerine güveni azaltılıyor;
        # güçlü trend'te (ADX>25) DI+/DI- yönü mevcut trend'i doğruluyorsa
        # hafifçe güçlendiriliyor.
        if context.adx < 20:
            caveats.append(f"ADX {context.adx:.1f} — weak/ranging trend, low conviction")
            score *= c.adx_weak_discount
        elif context.adx > 25:
            if context.di_plus > context.di_minus and context.trend == "bullish":
                score += c.adx_strong_confirm_weight
                evidence.append(f"ADX {context.adx:.1f} — strong trend, DI+ confirms bullish direction")
            elif context.di_minus > context.di_plus and context.trend == "bearish":
                score -= c.adx_strong_confirm_weight
                evidence.append(f"ADX {context.adx:.1f} — strong trend, DI- confirms bearish direction")

        # Faz 237: OBV ıraksaması — gerçek hacim akışı fiyatı desteklemiyorsa
        # (klasik "zayıf rally/zayıf düşüş" uyarısı) güveni azaltıyor.
        if context.price_obv_divergence == "bearish_divergence":
            caveats.append("Price rising but OBV falling — bearish volume divergence")
            score -= c.obv_divergence_weight
        elif context.price_obv_divergence == "bullish_divergence":
            caveats.append("Price falling but OBV rising — bullish volume divergence")
            score += c.obv_divergence_weight

        # Kendi hesapladığı yön ÖNCE belirleniyor — TradingView alarmı
        # sadece bir onay/uyarı notu ekliyor, kendi başına yönü belirlemiyor
        # ya da ezmiyor (Faz 193: "ikinci görüş" isteğinin doğrudan karşılığı).
        if score > 0.5:
            direction = "LONG"
        elif score < -0.5:
            direction = "SHORT"
        else:
            direction = "WAIT"

        if context.external_signal == "bullish":
            if direction == "LONG":
                evidence.append(f"TradingView alarmı teyit ediyor (kaynak: {context.external_signal_source})")
            elif direction == "SHORT":
                caveats.append("TradingView alarmı kendi teknik görüşümüzle çelişiyor (bullish alarm, bearish iç görüş)")
        elif context.external_signal == "bearish":
            if direction == "SHORT":
                evidence.append(f"TradingView alarmı teyit ediyor (kaynak: {context.external_signal_source})")
            elif direction == "LONG":
                caveats.append("TradingView alarmı kendi teknik görüşümüzle çelişiyor (bearish alarm, bullish iç görüş)")

        # Faz 194: Nasdaq+S&P500 korelasyonu — sadece ikisi de aynı yönde
        # anlaştığında bir sinyal var, ve yine sadece onay/uyarı notu,
        # kendi başına yönü belirlemiyor.
        if context.correlated_market_trend == "bullish":
            if direction == "LONG":
                evidence.append("Nasdaq + S&P500 ikisi de bullish — geleneksel risk-varlığı piyasalarıyla uyumlu")
            elif direction == "SHORT":
                caveats.append("Nasdaq + S&P500 bullish ama kendi teknik görüşümüz bearish — korelasyon çelişiyor")
        elif context.correlated_market_trend == "bearish":
            if direction == "SHORT":
                evidence.append("Nasdaq + S&P500 ikisi de bearish — geleneksel risk-varlığı piyasalarıyla uyumlu")
            elif direction == "LONG":
                caveats.append("Nasdaq + S&P500 bearish ama kendi teknik görüşümüz bullish — korelasyon çelişiyor")

        confidence = min(abs(score) / c.confidence_divisor, 0.85)

        return AgentOpinion(
            agent_id=self.agent_id,
            domain=AgentDomain.TECHNICAL,
            direction=direction,
            confidence=round(confidence, 3),
            evidence_strength=0.70,
            data_quality=0.85,
            freshness=0.90,
            source_reliability=0.75,
            evidence=evidence,
            caveats=caveats,
        ).recalculate()
