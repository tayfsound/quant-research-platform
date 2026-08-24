"""RiskContext – hash doğrulamalı immutable risk limitleri."""
from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, Field


class RiskAdjustmentSource(StrEnum):
    LLM = "llm"
    VOLATILITY_MODEL = "volatility_model"
    MANUAL = "manual"

class RiskReason(BaseModel):
    code: str
    message: str
    severity: str = "warning"  # "info", "warning", "critical"

class RiskLimitEntry(BaseModel):
    value: float
    hash: str = ""

    def verify(self, secret: str = "") -> bool:
        """Eğer hash boşsa (geliştirme modu) her zaman geçer."""
        if not self.hash:
            return True
        expected = sha256(f"{self.value}:{secret}".encode()).hexdigest()
        return expected == self.hash

class RiskAdjustment(BaseModel):
    source: RiskAdjustmentSource = RiskAdjustmentSource.MANUAL
    factor: float = 1.0

class RiskEvaluation(BaseModel):
    verdict: str = ""               # "approved" / "rejected"
    reasons: list[RiskReason] = Field(default_factory=list)

class RiskContext(BaseModel):
    limits: dict[str, RiskLimitEntry] = Field(default_factory=dict)
    current_exposure: float = 0.0
    current_drawdown: float = 0.0
    daily_pnl: float = 0.0
    adjustment: RiskAdjustment = Field(default_factory=RiskAdjustment)
    evaluation: RiskEvaluation = Field(default_factory=RiskEvaluation)
    # Faz 188: kullanıcının app_settings üzerinden kontrol ettiği operasyonel
    # sınırlar (bkz. services/risk_state.py) — "test" modunda RiskEngine tüm
    # kontrolleri atlar, "live" modunda hepsi devreye girer.
    trading_mode: str = "live"
    open_position_count: int = 0
    max_concurrent_positions: int | None = None
    capital_used_pct: float = 0.0
    max_capital_pct: float | None = None
    # Faz 358 — MAX_SAME_SYMBOL_DIRECTION_CAPITAL kontrolü mutlak $ tavanı
    # hesaplamak için gerçek starting_capital'a ihtiyaç duyuyor (capital_
    # used_pct gibi zaten oranlanmış bir değer değil).
    starting_capital: float | None = None
    # Faz 189: "stopsuz işlem yapmasın test modunda bile olsa" — bu ikisi
    # trading_mode="test" iken bile ATLANMAZ (aşağıdaki diğerlerinin
    # tersine), çünkü amaç sermaye riskini sınırlamak değil, art arda
    # anlamsız/gürültülü işlem açılmasını engellemek.
    seconds_since_last_trade: float | None = None
    min_seconds_between_trades: int | None = None
    # Faz 190: dashboard Start/Stop düğmesi — False iken yeni pozisyon
    # açılmaz, mevcut açık pozisyonlar (PositionCloser, ayrı bir yol)
    # bundan etkilenmez.
    ai_enabled: bool = True
    # Kill switch — gerçek olay (2026-08-12): 24 saatte 102 ardışık
    # stop-loss, hiçbir otomatik durdurma mekanizması yoktu, sadece manuel
    # Start/Stop vardı. consecutive_losses: en son kapanmış işlemlerden
    # (tüm semboller, kronolojik) geriye doğru, İLK kazançtan önceki
    # ardışık kayıp sayısı. kill_switch_consecutive_losses <= 0 ise
    # devre dışı (fail-closed varsayılan DEĞİL — kullanıcı açıkça bir eşik
    # belirlemeli, icat edilmiş bir sayı dayatılmıyor).
    consecutive_losses: int = 0
    kill_switch_consecutive_losses: int = 0
    # Faz 268-sonrası — gerçek olay (2026-08-13): AYNI sembolde AYNI yönde
    # onlarca pozisyon (ör. XAUTUSDT SHORT x54) art arda, önceki hiçbiri
    # kapanmadan açılabiliyordu — max_concurrent_positions TOPLAM sayıyı
    # sınırlıyor ama tek bir sembol/yön kombinasyonunun ne kadar
    # yığılabileceğine hiç bakmıyordu. ENB/Cross-Symbol Correlation Filter
    # de SADECE aynı cycle'da eşzamanlı önerilen sembollere bakıyor, saatler
    # boyunca BİRİKEN aynı-yönlü pozisyonu görmüyor. same_direction_open_
    # counts: {"LONG": n, "SHORT": m} — bu sembol için ŞU AN açık pozisyon
    # sayısı, yöne göre (bkz. services/risk_state.py). max_open_positions_
    # per_symbol_direction <=0/None ise devre dışı (icat edilmiş bir
    # varsayılan eşik dayatılmıyor, kullanıcı açıkça belirlemeli).
    same_direction_open_counts: dict[str, int] = Field(default_factory=dict)
    max_open_positions_per_symbol_direction: int | None = None
    # Faz 358 — kullanıcı bulgusu: yukarıdaki sayı-bazlı gate 1000'e
    # gevşetildiği için (kullanıcı isteğiyle, test modunda kısıtlama
    # gereksiz) fiilen devre dışı — ama "aynı sembol/yönde ne kadar $
    # bağlı" sorusuna hâlâ hiçbir gate bakmıyordu (ör. XAUTUSDT LONG'da
    # 17 pozisyon, hepsi %0.15'lik bir bantta). same_direction_open_
    # notional: {"LONG": $, "SHORT": $} — bu sembol için ŞU AN açık
    # GERÇEK marjin (kaldıraçtan bağımsız), yöne göre (bkz. services/
    # risk_state.py). max_same_symbol_direction_capital_pct <=0/None ise
    # devre dışı.
    same_direction_open_notional: dict[str, float] = Field(default_factory=dict)
    max_same_symbol_direction_capital_pct: float | None = None
    # Faz 268-sonrası — Concept Drift gate (bkz. services/risk_state.py::
    # load_position_risk_state, analytics/concept_drift.py). KASITLI
    # OLARAK burada, load_position_risk_state()'te ÖNCEDEN hesaplanıyor
    # (consecutive_losses ile AYNI desen) — RiskEngine.execute()'un
    # KENDİ İÇİNDE bir DB sorgusu yapmaması için: gerçek bir regresyon
    # bulundu (2026-08-13) — RiskEngine kendi içinde global, sembolsüz bir
    # sorgu yapınca, "far future" zaman damgalı sentetik veri üreten BAŞKA
    # testler (ör. test_risk_state.py) bu kontrolü yanlışlıkla tetikleyip
    # ilgisiz testleri kırdı. None = ya yetersiz veri ya da gerçek bir
    # drift tespit edilmedi (fail-closed).
    concept_drift_reason: RiskReason | None = None
