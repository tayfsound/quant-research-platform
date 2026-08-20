"""Faz 187: gerçek pozisyon kapanışı.

services/forward_outcome.py'nin "backtest tarzı" hesaplamasından farkı:
orada entry VE exit aynı anda, aynı zaten-var-olan geçmiş OHLCV penceresinden
okunuyordu (yani hiçbir zaman gerçekten zaman geçmesini beklemiyordu). Burada
entry_price pozisyon gerçekten açıldığı anda sabitlenmiş durumda, exit_price
ise gerçekten şimdi (kapanış anında) çekilen güncel fiyat — aradan gerçekten
en az `hold_seconds` kadar gerçek zaman geçmiş olmalı.
"""
from datetime import UTC, datetime

import structlog

from contracts.agent import VOTING_AGENT_DOMAINS
from contracts.agent_performance import AgentPerformanceRecord
from database.repositories.decision_persistor import DecisionPersistor
from market_data.ingestion.data_provider import OHLCVProvider
from market_data.market_hours import is_market_open
from services.agent_memory import AgentMemory
from services.memory_consolidator import MemoryConsolidator
from services.weight_optimizer import WeightOptimizer
from services.weight_repository import WeightRepository
from simulator.fee_engine import FeeEngine
from simulator.funding_cost import compute_funding_cost

# Faz 229: artık contracts/agent.py::VOTING_AGENT_DOMAINS — tek gerçek
# kaynak, services/learning_loop.py ve services/weight_optimizer.py da
# aynısını kullanıyor (bkz. o dosyalardaki "unknown" domain sızıntısı bulgusu).
_VALID_AGENT_DOMAINS = VOTING_AGENT_DOMAINS

logger = structlog.get_logger()

# Faz 268-sonrası — kullanıcının bir dış inceleme üzerinden gelen gerçek
# bulgusu: analytics/mae_mfe.py::compute_mae_mfe backtest'te var olup
# CANLI pozisyon kapanışlarında hiç çağrılmıyordu — "kayıp işlemlerin
# çoğunda MFE≥|MAE|" (fiyat lehte hareket etmiş ama stop'a takılmış)
# iddiası bu yüzden GERÇEK canlı veriyle doğrulanamıyordu (mae_pct/
# mfe_pct hiçbir zaman kaydedilmemişti). Bu, sadece hold süresi boyunca
# GERÇEK bar geçmişini (bir kerelik, SADECE pozisyon fiilen kapanırken —
# her açık pozisyon için her check cycle'ında DEĞİL, performans/rate-
# limit riskini önlemek için) çekip mae_pct/mfe_pct'yi outcome'a ekliyor.
_MAE_MFE_TIMEFRAME_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "1d": 86400,
}
_MAE_MFE_BAR_TIMEFRAME = "1m"
_MAE_MFE_MAX_BARS = 1000  # Binance'in gerçek tek-istek tavanı

# Faz 313 — "breakeven_stop" etiketi SADECE gerçekleşen kayıp, orijinal
# (ratchet öncesi) stop mesafesinin bu oranından KÜÇÜKSE kullanılır —
# yani ratchet mekanizması kaybı GERÇEKTEN en az yarı yarıya azaltmışsa.
# 0.5 icat edilmiş değil: "mekanizma anlamlı ölçüde işe yaradı mı"
# sorusuna en doğal, orta noktalı cevap — daha gevşek bir eşik (ör. 0.9)
# neredeyse tam-mesafe kayıpları bile "başabaş" gösterebilirdi.
_BREAKEVEN_LOSS_REDUCTION_THRESHOLD = 0.5


class PositionCloser:
    def __init__(
        self,
        data_provider: OHLCVProvider,
        hold_seconds: int = 600,
        fee_engine: FeeEngine | None = None,
    ):
        self.data_provider = data_provider
        self.hold_seconds = hold_seconds
        self.fee_engine = fee_engine or FeeEngine()
        self.agent_memory = AgentMemory()
        self.weight_optimizer = WeightOptimizer(
            agent_memory=self.agent_memory,
            weight_repository=WeightRepository(),
        )
        # Faz 268aj — kullanıcı isteği: episodic memory GERÇEK kapanışlarla
        # beslensin (bkz. MemoryConsolidator.record_real_episode). Faz 268j
        # CognitiveEngine.finalize()'daki sahte n-bar proxy beslemesini
        # kasıtlı kesmişti ama "gerçek kapanışlarla yeniden bağlanacak" diye
        # not düşülen iş hiç yapılmamıştı — burada tamamlanıyor.
        self.memory_consolidator = MemoryConsolidator()

    def _age_seconds(self, opened_at: datetime, now: datetime) -> float:
        # Bilinen borç (CURRENT_STATE.md'de dokümante): DB'de naive/aware
        # datetime karışık olabilir. Burada ikisini de kabul ediyoruz.
        if opened_at.tzinfo is None:
            return (now.replace(tzinfo=None) - opened_at).total_seconds()
        return (now - opened_at).total_seconds()

    def _compute_live_mae_mfe(self, symbol: str, direction: str, entry_price: float, age_seconds: float) -> dict:
        """Pozisyonun GERÇEKTEN açık kaldığı süre boyunca GERÇEK 1 dakikalık
        bar geçmişini çekip compute_mae_mfe ile (backtest'in kullandığı AYNI,
        zaten doğrulanmış fonksiyon) MAE/MFE hesaplar. Fetch başarısız
        olursa ya da eski bir pozisyon 1000 bar tavanını aşan bir hold
        süresine sahipse (Binance'in gerçek tek-istek tavanı) SADECE en son
        1000 dakikayı kapsar — bu durumda gerçek MAE daha erken oluşmuşsa
        eksik/düşük tahmin edilebilir, ama icat edilmiş bir sayı üretmekten
        iyidir. Herhangi bir hata GERÇEK kapanış işlemini ASLA engellemez
        (fail-closed DEĞİL, sessiz-başarısız — EventLogRepository.record()
        ile AYNI felsefe)."""
        try:
            from analytics.mae_mfe import compute_mae_mfe

            bar_seconds = _MAE_MFE_TIMEFRAME_SECONDS.get(_MAE_MFE_BAR_TIMEFRAME, 60)
            bars_needed = min(_MAE_MFE_MAX_BARS, max(2, int(age_seconds / bar_seconds) + 5))
            bars = self.data_provider.get_ohlcv(symbol, _MAE_MFE_BAR_TIMEFRAME, limit=bars_needed)
            if not bars:
                return {"mae_pct": None, "mfe_pct": None, "time_to_mae_seconds": None, "time_to_mfe_seconds": None}
            return compute_mae_mfe(direction, entry_price, bars)
        except Exception:
            logger.warning("live_mae_mfe_computation_failed", symbol=symbol)
            return {"mae_pct": None, "mfe_pct": None, "time_to_mae_seconds": None, "time_to_mfe_seconds": None}

    def _exit_reason(self, direction: str, current_price: float, stop_loss_price, take_profit_price) -> str | None:
        """Faz 192: gerçek fiyat, gerçek stop/target seviyesine ulaştı mı?
        Vade dolmasını beklemeden hemen kapatmak için — hold_seconds sadece
        hiçbir hedef/stop tanımlı değilse ya da hiçbiri tetiklenmemişse
        devreye giren bir üst sınır."""
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

    def _record_agent_learning(self, pos: dict, pnl: float) -> bool:
        """Faz 210: gerçek bulgu — PositionCloser gerçekten açılıp gerçekten
        kapanan pozisyonların pnl'ini decisions tablosuna yazıyordu, ama
        bu sonucu hiçbir kod AgentMemory/WeightOptimizer'a geri
        beslemiyordu. services/learning_loop.py::process_outcome() bunun
        için yazılmıştı ama onu tetikleyecek tek mekanizma (Pending
        OutcomeTracker.run_scheduler) hiç başlatılmıyordu ve zaten kırıktı
        (bkz. services/pending_outcome_tracker.py, artık kaldırıldı).
        Burada gerçek kapanışın kendi anında, decisions.agent_contributions'
        taki (zaten SELECT * ile elimizde) gerçek görüşleri doğrudan
        AgentMemory'ye yazıyoruz.

        Faz 211: kritik düzeltme — önceki hali işlemin genel kârlılığını
        (pnl>0) FARKINDA OLMADAN her ajana (yön ne olursa olsun, WAIT dahil)
        uyguluyordu; ters yön öneren ya da WAIT diyen bir ajan bile işlem
        kârlıysa "doğru" işaretleniyordu. Artık her ajanın KENDİ önerdiği
        yön ile gerçekten alınan işlemin yönü karşılaştırılıyor: aynı
        yöndeyse doğruluğu işlemin kârlılığıyla; farklıysa (ters yön ya da
        WAIT — ikisi de o işleme "hayır" demek) doğruluğu işlemin ZARARIYLA
        (yani o işleme girmemiş/karşı çıkmış olmanın haklı çıkmasıyla)
        ölçülüyor.

        Faz 245: kritik bulgu — Faz 211'in "WAIT = zararlıysa doğru"
        kuralı, sistemin genel kazanma oranı düşükken (şu an %23.6) HER
        ZAMAN WAIT diyen bir ajanı gerçek yön tahmini becerisi olmadan
        (sadece taban oranı sayesinde) yapay olarak yüksek doğrulukla
        ödüllendiriyordu — gerçek veride onchain/time/epistemology
        domain'leri TEK BİR KEZ bile yönlü oy vermemiş, yine de WeightOptimizer
        'ları %83-89 "doğru" görüyordu. WAIT bir yön tahmini değil, bir
        çekimser kalma — kâr/zararla "doğru/yanlış" ölçülemez. Artık SADECE
        gerçekten yönlü (LONG/SHORT) oy veren ajanlar kaydediliyor; WAIT
        diyen bir ajan ne ödüllendiriliyor ne cezalandırılıyor, sadece o
        işlem için ölçülmüyor — WeightOptimizer'ın gördüğü doğruluk artık
        SADECE gerçekten yön tahmini yapıldığında ölçülen gerçek beceriyi
        yansıtıyor.

        Faz 282 — kritik bulgu: excluded_from_stats=true (bilinen bir
        bug'dan kirlenmiş, ör. pump_fade/scalp/hedge migration'larıyla
        işaretlenmiş) bir karar, dashboard/istatistik sorgularının
        hepsinde hariç tutuluyordu ama BURADA hiç kontrol edilmiyordu —
        AgentMemory'ye (ve oradan WeightOptimizer/SourceReliabilityAgent
        öğrenmesine) sızmaya devam ediyordu. reliability_legacy_cutoff_at
        sadece decision_opened_at'e göre ZAMAN tabanlı filtreliyor;
        excluded_from_stats'ın kapsadığı (özellikle kesimden SONRA açılıp
        bilinen bir bug'dan etkilenen) satırları yakalamıyor. Artık
        işaretli kararlar ajan öğrenmesine de hiç girmiyor — "hiç
        açılmamış gibi" davranış tüm sistemde tutarlı."""
        if pos.get("excluded_from_stats"):
            return False

        contributions = pos.get("agent_contributions") or []
        symbol = pos["symbol"]
        executed_direction = (pos.get("direction") or "").upper()
        profitable = pnl > 0

        # Faz 258 (mimari inceleme bulgusu, doğrulandı): market_regime hiç
        # set edilmiyordu — AgentPerformanceSummary.by_regime, GERÇEK
        # (canlı) kapanışlar için her zaman boş kalıyordu, "hangi ajan
        # hangi rejimde iyi" sorusu hiç cevaplanamıyordu. market_snapshot
        # zaten agent_contributions içinde duruyor (decision_persistor.py),
        # sadece hiç okunmuyordu.
        #
        # Faz 268s — kritik bulgu: market_regime SADECE trend'i (bullish/
        # bearish/neutral) yakalıyordu, volatility_regime (low/normal/
        # high — TechnicalContext'te zaten gerçekten var olan bir alan)
        # hiç dahil edilmiyordu. "Yüksek volatilitede hangi ajan iyi?"
        # sorusu hiç cevaplanamıyordu — ör. bir trend-takip ajanı sakin
        # bir "bullish" rejimde iyi olup yüksek volatiliteli whipsaw'da
        # kötü olabilir, ama ikisi de tek "bullish" etiketi altında
        # karışıyordu. trend bilinmiyorsa (gerçek market_snapshot yoksa)
        # hâlâ "unknown" — volatility'yi trend'siz birleştirmek anlamsız.
        market_regime = self._extract_market_regime(pos)

        recorded = False
        for item in contributions:
            domain = item.get("domain")
            if domain not in _VALID_AGENT_DOMAINS:
                continue
            agent_direction = (item.get("direction") or "").upper()
            if agent_direction not in ("LONG", "SHORT"):
                continue
            was_correct = profitable if agent_direction == executed_direction else not profitable
            self.agent_memory.record(AgentPerformanceRecord(
                agent_domain=domain,
                direction=item.get("direction", ""),
                confidence=item.get("confidence", 0.0) or 0.0,
                was_correct=was_correct,
                pnl=pnl,
                symbol=symbol,
                market_regime=market_regime,
                decision_opened_at=pos.get("opened_at"),
            ))
            recorded = True

        return recorded

    def _extract_features(self, pos: dict) -> dict:
        for item in pos.get("agent_contributions") or []:
            if isinstance(item, dict) and item.get("type") == "market_snapshot":
                return ((item.get("data") or {}).get("features")) or {}
        return {}

    def _extract_market_regime(self, pos: dict) -> str:
        """Faz 258/268s/268b — açılış anındaki gerçek trend+volatility'den
        "trend_volatility" formatında piyasa rejimi (bkz. engines/
        cognitive_pipeline.py::CouncilStage'in karar anında hesapladığı
        AYNI format — regime-özel snapshot'ların doğru seçilebilmesi bu
        ikisinin birebir eşleşmesine bağlı)."""
        features = self._extract_features(pos)
        trend = features.get("trend", "unknown")
        if trend == "unknown":
            return "unknown"
        volatility = features.get("volatility_regime", "normal")
        return f"{trend}_{volatility}"

    def _record_episodic_memory(self, pos: dict, pnl: float, exit_reason: str) -> None:
        """Faz 268aj — gerçek kapanışı episodic memory'ye yazar (bkz.
        MemoryConsolidator.record_real_episode). Bir hata pozisyon
        kapanışını asla engellemiyor — episodic hafıza ikincil bir
        sonuç, gerçek para hareketini (kapanışın kendisini) bloklamamalı."""
        try:
            self.memory_consolidator.record_real_episode(
                cycle_id=pos.get("id"),
                symbol=pos["symbol"],
                features=self._extract_features(pos),
                decision=(pos.get("direction") or "WAIT"),
                outcome={"pnl": pnl, "win": pnl > 0, "exit_reason": exit_reason},
            )
        except Exception as exc:
            logger.warning("episodic_memory_record_failed", symbol=pos.get("symbol"), error=str(exc))

    def estimate_net_pnl_if_closed_now(self, pos: dict, current_price: float) -> float:
        """Faz 268p — kullanıcı isteği: "hem her pozisyonun anlık kâr/
        zararını göster, hem kârdakileri toplu kapat ama komisyona
        ezilmeyecek şekilde." Aynı formül İKİSİ için de kullanılıyor —
        dashboard'da gösterilen sayı ile toplu kapamanın "kârlı mı"
        kararı asla birbirinden farklı çıkmasın diye. close_partial()'ın
        fraction=1.0 ile kullandığı AYNI ücret varsayımı (giriş+çıkış
        taker) — bu GERÇEKTEN kapatılırsa cebe geçecek net rakam, ham
        (komisyonsuz) bir sayı değil."""
        entry_price = pos.get("entry_price")
        quantity = pos.get("quantity") or 0.0
        direction = (pos.get("direction") or "").upper()
        if entry_price is None or quantity <= 0 or current_price is None:
            return 0.0

        if direction == "LONG":
            gross_pnl = (current_price - entry_price) * quantity
        elif direction == "SHORT":
            gross_pnl = (entry_price - current_price) * quantity
        else:
            return 0.0

        fee = self.fee_engine.calculate(entry_price * quantity) + self.fee_engine.calculate(
            current_price * quantity
        )

        funding_cost = 0.0
        opened_at = pos.get("opened_at")
        leverage = pos.get("leverage") or 1.0
        if leverage > 1.0 and opened_at is not None:
            funding_cost = compute_funding_cost(
                symbol=pos.get("symbol", ""), direction=direction,
                notional=entry_price * quantity,
                opened_at=opened_at, closed_at=datetime.now(UTC),
            )

        return gross_pnl - fee - funding_cost

    def close_partial(
        self,
        decision_repo: DecisionPersistor,
        decision_id: str,
        fraction: float,
        timeframe: str = "1m",
    ) -> dict:
        """Faz 268 — kullanıcı isteği: "pozisyonun yarısını/çeyreğini
        kademeli kapatabilen mekanizma." close_due_positions()'un aksine bu
        stop/target/likidasyon fiyatına bağlı DEĞİL — kullanıcı manuel
        olarak "şu an kârın bir kısmını realize et" diyor. fraction=1.0
        pratikte tam kapanışla aynı (decision_repo.close_position), ama
        önceki kısmi kapanışlardan birikmiş realized_pnl varsa ona
        ekleniyor — closed_trades_summary()'nin toplam pnl'i hep doğru
        kalsın diye."""
        if not (0 < fraction <= 1):
            raise ValueError("fraction must be in (0, 1]")

        pos = decision_repo.get_by_id(decision_id)
        if pos is None or pos.get("status") != "open":
            raise ValueError(f"decision {decision_id} not open")

        symbol = pos["symbol"]
        entry_price = pos.get("entry_price")
        quantity = pos.get("quantity") or 0.0
        direction = (pos.get("direction") or "").upper()
        if entry_price is None or quantity <= 0:
            raise ValueError(f"decision {decision_id} has no closeable quantity")

        data = self.data_provider.get_ohlcv(symbol, timeframe, limit=1)
        if not data:
            raise ValueError(f"no current price available for {symbol}")
        exit_price = data[-1].close

        # Faz 239'un close_due_positions'taki aynı sağlamlık kontrolü —
        # bariz bozuk/mock bir fiyatla manuel kapanış da yapılmasın.
        if exit_price <= 0 or exit_price > entry_price * 20 or exit_price < entry_price / 20:
            raise ValueError(f"suspicious current price for {symbol}: {exit_price}")

        close_qty = quantity * fraction
        if direction == "LONG":
            gross_pnl = (exit_price - entry_price) * close_qty
        elif direction == "SHORT":
            gross_pnl = (entry_price - exit_price) * close_qty
        else:
            gross_pnl = 0.0

        fee = self.fee_engine.calculate(entry_price * close_qty) + self.fee_engine.calculate(
            exit_price * close_qty
        )
        now = datetime.now(UTC)

        funding_cost = 0.0
        opened_at = pos.get("opened_at")
        leverage = pos.get("leverage") or 1.0
        if leverage > 1.0 and opened_at is not None:
            funding_cost = compute_funding_cost(
                symbol=symbol, direction=direction,
                notional=entry_price * close_qty,
                opened_at=opened_at, closed_at=now,
            )

        pnl = gross_pnl - fee - funding_cost

        # fraction'ı 1.0'a çok yakın vermek (ör. kalan miktarın tamamı)
        # gerçek bir tam kapanış — status='open' kalan, quantity'si ~0 olan
        # bir "hayalet" pozisyon bırakmamak için bu durumda close_position
        # çağrılıyor (önceki kısmi kapanışlardan birikmiş realized_pnl dahil).
        remaining_qty = quantity - close_qty
        if remaining_qty <= max(1e-8, quantity * 1e-6):
            existing_outcome = pos.get("outcome") or {}
            realized_pnl = float(existing_outcome.get("realized_pnl") or 0.0) + pnl
            decision_repo.close_position(
                decision_id=str(pos["id"]),
                exit_price=exit_price,
                pnl=realized_pnl,
                closed_at=now,
                outcome={
                    **existing_outcome,
                    "pnl": realized_pnl,
                    "gross_pnl": gross_pnl,
                    "fee": fee,
                    "win": realized_pnl > 0,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "quantity": quantity,
                    "exit_reason": "manual_full",
                },
                market_regime=self._extract_market_regime(pos),
            )
            self._record_agent_learning(pos, pnl)
            self._record_episodic_memory(pos, realized_pnl, "manual_full")
            return {"fully_closed": True, "exit_price": exit_price, "pnl": pnl, "realized_pnl": realized_pnl}

        result = decision_repo.close_position_partial(
            decision_id=str(pos["id"]),
            close_qty=close_qty,
            exit_price=exit_price,
            pnl=pnl,
            fee=fee,
            exit_reason="manual_partial",
            closed_at=now,
        )
        self._record_agent_learning(pos, pnl)
        return {"fully_closed": False, "exit_price": exit_price, "pnl": pnl, **result}

    def _apply_breakeven_stop(
        self, pos: dict, current_price: float, decision_repo: DecisionPersistor
    ) -> float | None:
        """Faz 268ae — kullanıcı isteği: "pozisyon kârlı gidiyor ama işler
        tersine döndü, stop yükseltilse tam zarar yerine nötr/az zararla
        çıkabilir." Gerçek veri bulgusu: son 30 günde stop_loss çıkışları
        -$2422 kaybettirdi, take_profit çıkışları sadece +$130 kazandırdı —
        oran, RiskTargetStage'in kurduğu 1:4 hedef/stop oranının tam
        tersi. stop_loss_price açılışta bir kez set edilip hiç
        değişmiyordu (bkz. update_stop_loss_price docstring) — kârlı
        açılıp geri dönen pozisyonlar tam stop mesafesini yiyordu.

        "N kâra ulaşınca stopu girişe çek" kuralı: fiyat, ilk risk
        mesafesinin (|entry-stop|) breakeven_trigger_r_multiple katı
        kadar LEHTE hareket ettiyse stop girişe (başabaş) çekilir.
        SADECE bir kez tetiklenir (stop zaten girişe eşitse tekrar işlem
        yapmaz) ve SADECE sıkılaştırır, asla gevşetmez — riski hiçbir
        zaman artırmıyor.

        Faz 269-sonrası — kullanıcı bulgusu: TAM 1R (multiplier=1.0)
        gerçek veride bazı pozisyonlar (ör. pump_fade_v1, 5x kaldıraçlı
        az likit coinler) için hiç ulaşılamayan bir eşikti — sadece
        %1-1.8 lehte gidip ters dönüp likidasyona kadar gitti, koruma
        hiç devreye giremedi. Eşik artık AppSettings'ten okunuyor
        (varsayılan 0.5R) — redeploy gerekmeden hızla ayarlanabilir.

        Faz 269-sonrası (2) — kullanıcı bulgusu: pump_fade pozisyonları
        ~$2k kârdayken piyasa tersine dönüp ~-$2k zarara kadar gidebiliyordu
        — breakeven TEK BAŞINA yetersiz, çünkü SADECE net zararı önlüyor,
        GERÇEK kârı hiç KİLİTLEMİYOR (girişe çekilen stop yine de $0
        sonuç demek). Artık buna ek olarak sabit yüzdelik bir trailing
        stop da uygulanıyor — entry_price'a göre SABİT mesafe (mutasyona
        uğrayan stop_loss_price'a göre DEĞİL, entry_price hiç değişmeyen
        güvenilir bir referans): fiyat lehte gittikçe stop (current_price
        ∓ entry_price*trailing_pct) olarak arkadan takip eder. Breakeven
        ve trailing'in ürettiği adaylardan HANGİSİ daha sıkıysa (daha çok
        kâr koruyorsa) o kullanılır — ikisi de SADECE sıkılaştırır.

        Faz 282 — kritik bulgu (2026-08-19, kullanıcı: "kardayken -4k dolar
        zarar yazmaya başladıysa çok mantıksız"): yukarıdaki breakeven_
        trigger_r_multiple/trailing_stop_distance_pct, pump_fade_v1'in
        SABİT geniş stop mesafesine (pump_fade_stop_distance_pct=%30) göre
        ORANTILI hesaplanıyor — %50 tetikleme oranı bile mutlak %15
        (0.5*%30) demek. Gerçek veri (7 açık pozisyon, 2026-08-19): hepsi
        gerçek kâra geçti (MFE %0.4-%5.0) ama HİÇBİRİ ne %15 breakeven
        eşiğine ne %5 trailing eşiğine ulaşamadı — koruma fiilen hiç
        devreye giremedi, hepsi kârdan zarara döndü. pump_fade_v1
        pozisyonları artık entry_price'a göre AYRI, MUTLAK yüzdelik
        eşikler kullanıyor (stop mesafesiyle orantılı DEĞİL) — diğer (AI
        konseyi) pozisyonlarının davranışı DEĞİŞMEDİ."""
        entry_price = pos.get("entry_price")
        stop_loss_price = pos.get("stop_loss_price")
        direction = (pos.get("direction") or "").upper()
        if entry_price is None or stop_loss_price is None or direction not in ("LONG", "SHORT"):
            return stop_loss_price

        is_pump_fade = pos.get("experiment_bucket") == "pump_fade_v1"
        if is_pump_fade:
            breakeven_trigger_pct = self._load_pump_fade_breakeven_trigger_pct()
            trailing_pct = self._load_pump_fade_trailing_stop_distance_pct()
        else:
            trigger_r_multiple = self._load_breakeven_trigger_r_multiple()
            trailing_pct = self._load_trailing_stop_distance_pct()

        if direction == "LONG":
            original_risk = entry_price - stop_loss_price
            candidates = [stop_loss_price]
            if is_pump_fade:
                if current_price >= entry_price * (1 + breakeven_trigger_pct):
                    candidates.append(entry_price)
            elif original_risk > 0 and current_price >= entry_price + original_risk * trigger_r_multiple:
                candidates.append(entry_price)
            if trailing_pct > 0:
                trailing_candidate = current_price - entry_price * trailing_pct
                # Trailing SADECE gerçek kâr bölgesinde (entry_price'ın
                # ÜSTÜNDE bir aday) devreye girer — aksi halde henüz hiç
                # lehte hareket olmadan (ya da zarardayken) trailing_pct,
                # RiskTargetStage'in özenle hesapladığı geniş ATR-tabanlı
                # stop'u erken ve haksız yere sıkılaştırabilirdi.
                if trailing_candidate > entry_price:
                    candidates.append(trailing_candidate)
            new_stop = max(candidates)
        else:
            original_risk = stop_loss_price - entry_price
            candidates = [stop_loss_price]
            if is_pump_fade:
                if current_price <= entry_price * (1 - breakeven_trigger_pct):
                    candidates.append(entry_price)
            elif original_risk > 0 and current_price <= entry_price - original_risk * trigger_r_multiple:
                candidates.append(entry_price)
            if trailing_pct > 0:
                trailing_candidate = current_price + entry_price * trailing_pct
                if trailing_candidate < entry_price:
                    candidates.append(trailing_candidate)
            new_stop = min(candidates)

        if new_stop != stop_loss_price:
            decision_repo.update_stop_loss_price(str(pos["id"]), new_stop)
        return new_stop

    @staticmethod
    def _load_trailing_stop_distance_pct() -> float:
        """0.0 = trailing kapalı (sadece breakeven). entry_price'a göre
        sabit mesafe — min_stop_pct (%4.5) tabanıyla tutarlı bir varsayılan
        (%5): kâr kilitlemeyi hızlandıracak kadar sıkı, pump-fade'in doğal
        oynaklığıyla anında tetiklenmeyecek kadar geniş."""
        try:
            from database.repositories.app_settings_repository import AppSettingsRepository
            from database.session_factory import SessionFactory

            with SessionFactory.get_session() as session:
                value = float(AppSettingsRepository(session).get("trailing_stop_distance_pct") or 0.05)
            return value if value >= 0.0 else 0.05
        except Exception as exc:
            logger.warning("trailing_stop_distance_pct_load_failed", error=str(exc))
            return 0.05

    @staticmethod
    def _load_breakeven_trigger_r_multiple() -> float:
        try:
            from database.repositories.app_settings_repository import AppSettingsRepository
            from database.session_factory import SessionFactory

            with SessionFactory.get_session() as session:
                value = float(AppSettingsRepository(session).get("breakeven_trigger_r_multiple") or 0.5)
            return value if 0.0 < value <= 1.0 else 0.5
        except Exception as exc:
            logger.warning("breakeven_trigger_r_multiple_load_failed", error=str(exc))
            return 0.5

    @staticmethod
    def _load_pump_fade_breakeven_trigger_pct() -> float:
        """pump_fade_v1 için MUTLAK yüzdelik breakeven eşiği — bkz.
        _apply_breakeven_stop docstring'indeki Faz 282 notu."""
        try:
            from database.repositories.app_settings_repository import AppSettingsRepository
            from database.session_factory import SessionFactory

            with SessionFactory.get_session() as session:
                value = float(AppSettingsRepository(session).get("pump_fade_breakeven_trigger_pct") or 0.01)
            return value if value > 0.0 else 0.01
        except Exception as exc:
            logger.warning("pump_fade_breakeven_trigger_pct_load_failed", error=str(exc))
            return 0.01

    @staticmethod
    def _load_pump_fade_trailing_stop_distance_pct() -> float:
        """pump_fade_v1 için MUTLAK yüzdelik trailing mesafesi — bkz.
        _apply_breakeven_stop docstring'indeki Faz 282 notu."""
        try:
            from database.repositories.app_settings_repository import AppSettingsRepository
            from database.session_factory import SessionFactory

            with SessionFactory.get_session() as session:
                value = float(AppSettingsRepository(session).get("pump_fade_trailing_stop_distance_pct") or 0.007)
            return value if value >= 0.0 else 0.007
        except Exception as exc:
            logger.warning("pump_fade_trailing_stop_distance_pct_load_failed", error=str(exc))
            return 0.007

    def close_due_positions(self, decision_repo: DecisionPersistor, timeframe: str = "1m") -> list[dict]:
        """Açık pozisyonları gerçek güncel fiyatla kontrol eder: fiyat gerçek
        stop-loss/take-profit seviyesine ulaştıysa kapatır. Başka HİÇBİR
        sebeple kapatmaz.

        Faz 215: kritik bulgu — vade dolunca kapatma (time_expired)
        kaldırıldı. Kullanıcının kendi sözleriyle: "bile bile zarar etmek
        demek bu." Gerçek veriyle doğrulandı: trade_horizon (10 dk) <
        candle_timeframe (15 dk) olduğunda kapanan işlemlerin %64'ü
        stop/target'a hiç ulaşmadan, sadece vade dolduğu için (küçük
        komisyon kaybıyla) kapanıyordu — sinyal kalitesinden tamamen
        bağımsız, yapay/kaçınılmaz bir kayıp mekanizmasıydı. Artık bir
        pozisyon SADECE gerçekten TP ya da SL'e ulaştığında kapanır —
        ne kadar sürerse sürsün. (hold_seconds/trade_horizon artık burada
        kullanılmıyor; DecisionFusion'ın Negative EV kapısı zaten
        stop_loss_price/take_profit_price'ı hiç set edilmemiş bir
        pozisyonun asla "open" statüsüne ulaşmasına izin vermiyor, yani
        sonsuza kadar açık kalacak bir pozisyon riski yok.)"""
        now = datetime.now(UTC)
        closed = []
        learned_any = False
        regimes_seen: set[str] = set()

        # Faz 269-sonrası — KRİTİK bulgu: burası varsayılan limit=200 ile
        # çağrılıyordu ama gerçek açık pozisyon sayısı 200'ü çoktan
        # aşmıştı (2631) — ORDER BY opened_at DESC yüzünden en eski
        # binlerce pozisyon (bazıları %20+ kârda) bu döngüye HİÇ
        # girmiyordu, stop/hedef/likidasyon/breakeven/trailing kontrolü
        # sonsuza kadar atlanıyordu. limit=None artık TÜM açık
        # pozisyonları kontrol ediyor.
        for pos in decision_repo.list_open_positions(limit=None):
            opened_at = pos.get("opened_at")
            entry_price = pos.get("entry_price")
            if opened_at is None or entry_price is None:
                continue

            symbol = pos["symbol"]
            quantity = pos.get("quantity") or 0.0
            direction = (pos.get("direction") or "").upper()
            age = self._age_seconds(opened_at, now)

            # Faz 244: kritik bulgu — hisse/endeks/emtia pozisyonları (MSFT,
            # NVDA, AAPL, ^GSPC, ^IXIC) piyasa kapalıyken (gece, hafta sonu)
            # bile her dakika kontrol ediliyordu; YahooProvider bu durumda
            # hata vermek yerine GERÇEK ama ESKİ (dünün kapanışı, saatlerce
            # bayat) bir fiyat döndürüyor — bu "şu anki fiyat" gibi
            # kullanılıp pozisyon kapatma/stop-target kararına giriyordu.
            # run_trading_cycle_task zaten aynı market_hours kontrolünü
            # YENİ pozisyon açarken uyguluyordu (Faz 195); burada da aynısı
            # gerekiyor — piyasa kapalıyken kapanış denemesini tamamen atla,
            # bayat fiyatla karar verme.
            if not is_market_open(symbol, now):
                continue

            data = self.data_provider.get_ohlcv(symbol, timeframe, limit=1)
            if not data:
                continue
            current_price = data[-1].close

            # Faz 239: kritik bulgu — MARKET_DATA_FALLBACK_TO_MOCK=True
            # iken gerçek Binance isteği başarısız olduğunda sessizce
            # sembolden bağımsız ~$50,000 mock fiyata düşülüyordu (artık
            # varsayılan olarak kapalı, bkz. config/settings.py). İkinci,
            # bağımsız bir güvenlik katmanı: entry_price'a göre 20 kattan
            # fazla sapan bir "güncel fiyat" gerçek bir piyasa hareketi
            # olamaz (bu sistemin işlem yaptığı hiçbir varlık — major
            # kripto, hisse, endeks, altın-destekli token — bir pozisyonun
            # ömrü içinde böyle bir hareket yapmaz) — başka bir yoldan
            # benzer bir bug sızarsa bile gerçek olmayan bir fiyatla
            # pozisyon kapatılmasını engeller.
            if current_price <= 0 or current_price > entry_price * 20 or current_price < entry_price / 20:
                logger.warning(
                    "position_closer_suspicious_price_skipped",
                    symbol=symbol, entry_price=entry_price, current_price=current_price,
                )
                continue

            pos["stop_loss_price"] = self._apply_breakeven_stop(pos, current_price, decision_repo)

            # Faz 255: kullanıcı isteği — kaldıraç desteği. Kaldıraçlı bir
            # pozisyon (leverage>1) gerçek likidasyon fiyatına ulaşırsa,
            # bu stop-loss'tan ÖNCE kontrol edilir — gerçek bir kaldıraçlı
            # pozisyon likidasyona uğrarsa sistem bunu görmezden gelemez
            # (fail-fake olmaz). "liquidation" ayrı, açıkça etiketlenmiş
            # bir exit_reason — normal stop_loss ile karışmıyor.
            liquidation_price = pos.get("liquidation_price")
            liquidated = liquidation_price is not None and (
                (direction == "LONG" and current_price <= liquidation_price)
                or (direction == "SHORT" and current_price >= liquidation_price)
            )
            if liquidated:
                exit_reason = "liquidation"
                exit_price = liquidation_price
            else:
                exit_reason = self._exit_reason(
                    direction, current_price, pos.get("stop_loss_price"), pos.get("take_profit_price")
                )
                if exit_reason is None:
                    continue
                exit_price = current_price

            if direction == "LONG":
                gross_pnl = (exit_price - entry_price) * quantity
            elif direction == "SHORT":
                gross_pnl = (entry_price - exit_price) * quantity
            else:
                gross_pnl = 0.0

            # Faz 223: kullanıcı isteği — "işlem ücretlerinden kurtulmanın
            # ya da minimize etmenin yolları var mı." Gerçek bulgu: çıkış
            # her zaman taker oranıyla (%0.05) ücretlendiriliyordu, giriş
            # gibi. Ama take_profit çıkışı gerçekte hedef fiyata önceden
            # oturmuş bir LIMIT emrinin dolmasıdır — gerçek borsalarda bu
            # "maker" sayılır (%0.02, 2.5x daha ucuz). stop_loss ise gerçek
            # borsalarda tetiklenince MARKET emrine dönüşür — taker kalmalı
            # (%0.05). Giriş her zaman anlık/reaktif karar olduğu için
            # (bekleyen bir limit emri modellenmiyor, slippage zaten taker
            # maliyetini temsil ediyor) taker kalıyor.
            exit_is_maker = exit_reason == "take_profit"
            fee = self.fee_engine.calculate(entry_price * quantity) + self.fee_engine.calculate(
                exit_price * quantity, is_maker=exit_is_maker
            )

            # Faz 268-sonrası: funding rate maliyeti — SADECE kaldıraçlı
            # (leverage>1, "spot değil, gerçek perpetual" — bkz. Faz 255)
            # pozisyonlar için. Spot (leverage=1.0, bu sistemde kasıtlı
            # olarak "kaldıraçsız" anlamına geliyor) hiçbir zaman funding
            # ödemez/almaz — gerçek borsa mekaniğiyle tutarlı.
            funding_cost = 0.0
            leverage = pos.get("leverage") or 1.0
            if leverage > 1.0:
                funding_cost = compute_funding_cost(
                    symbol=symbol, direction=direction,
                    notional=entry_price * quantity,
                    opened_at=opened_at, closed_at=now,
                )

            pnl = gross_pnl - fee - funding_cost

            # Kullanıcı bulgusu (2026-08-19, gerçek CHIPUSDT örneği): dashboard
            # "stop_loss" etiketini her zaman zarar sanıyordu, ama breakeven/
            # trailing stop (pump_fade_v1 dahil, bkz. _apply_breakeven_stop)
            # fiyatı KÂRA doğru da taşıyabiliyor. İlk düzeltme SADECE stop
            # fiyatının entry'ye göre KONUMUNA bakıyordu (mekanizma) — ama
            # gerçek bir XAIUSDT örneği bunun da yanlış olduğunu gösterdi:
            # stop ham fiyatta entry'nin az ötesine (kâr yönünde) taşınmıştı
            # ama ücret+funding maliyeti net pnl'i -$54.95'e (gerçek zarar)
            # çekmişti — dashboard "kârda kapandı" diye etiketlemişti, PNL
            # eksi gösterirken. Artık NİHAİ (ücret+funding sonrası GERÇEK)
            # pnl birincil sinyal — "trailing_stop_profit" SADECE pnl
            # gerçekten pozitifken kullanılıyor, hiçbir zaman gösterilen
            # pnl işaretiyle çelişmiyor.
            #
            # Faz 313 — kullanıcı bulgusu (2026-08-20, gerçek KAIAUSDT/
            # PENDLEUSDT/HUMAUSDT/NOMUSDT/RPLUSDT örnekleri): "başabaş
            # çekilmiş görünen pozisyonlar zararla kapanmış." Kök neden:
            # stop_moved_toward_or_past_entry SADECE mekanizmanın (stop'un
            # KONUMU) çalıştığını doğruluyordu, gerçekleşen kaybın
            # ORİJİNAL (ratchet öncesi) stop mesafesine göre GERÇEKTEN
            # küçültülüp küçültülmediğini hiç kontrol etmiyordu — periyodik
            # kontrol döngüsü sırasında fiyat, ratchet edilmiş (girişe
            # yakın) stopu büyük bir kaymayla (slippage/gap) aşıp gerçek,
            # büyük bir kayıp üretebiliyordu (KAIAUSDT: fiyat-kaynaklı kayıp
            # -$1103.31, ücret+funding sadece -$55.50). Artık GERÇEK kayıp,
            # decisions.original_stop_loss_price'ta (pozisyon açılışında
            # bir kez yazılan, ratchet'in ASLA değiştirmediği ham değer)
            # saklı orijinal risk mesafesinin belirgin bir kısmından
            # (yarısından) küçükse "breakeven_stop" — mekanizma gerçekten
            # işe yaramış demektir. Orijinal değer yoksa (migration öncesi
            # açılmış eski bir pozisyon) fail-closed: doğrulanamıyor,
            # dürüstçe "stop_loss" kalır.
            if exit_reason == "stop_loss":
                stop_price = pos["stop_loss_price"]
                stop_moved_toward_or_past_entry = (
                    (direction == "LONG" and stop_price >= entry_price)
                    or (direction == "SHORT" and stop_price <= entry_price)
                )
                if pnl > 0:
                    exit_reason = "trailing_stop_profit"
                elif stop_moved_toward_or_past_entry:
                    original_stop_price = pos.get("original_stop_loss_price")
                    if original_stop_price is not None:
                        original_risk_amount = abs(entry_price - original_stop_price) * quantity
                        if (
                            original_risk_amount > 0
                            and abs(pnl) < original_risk_amount * _BREAKEVEN_LOSS_REDUCTION_THRESHOLD
                        ):
                            exit_reason = "breakeven_stop"

            # Faz 268-sonrası: SADECE burada (pozisyon fiilen kapanırken,
            # her check cycle'ında değil) gerçek MAE/MFE hesaplanıyor —
            # backtest'in zaten kullandığı AYNI fonksiyon, canlı ilk kez.
            mae_mfe = self._compute_live_mae_mfe(symbol, direction, entry_price, age)

            market_regime = self._extract_market_regime(pos)
            decision_repo.close_position(
                decision_id=str(pos["id"]),
                exit_price=exit_price,
                pnl=pnl,
                closed_at=now,
                outcome={
                    "pnl": pnl,
                    "gross_pnl": gross_pnl,
                    "fee": fee,
                    "funding_cost": funding_cost,
                    "win": pnl > 0,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "quantity": quantity,
                    "hold_seconds": age,
                    "exit_reason": exit_reason,
                    "mae_pct": mae_mfe["mae_pct"],
                    "mfe_pct": mae_mfe["mfe_pct"],
                    "time_to_mae_seconds": mae_mfe["time_to_mae_seconds"],
                    "time_to_mfe_seconds": mae_mfe["time_to_mfe_seconds"],
                },
                market_regime=market_regime,
            )
            closed.append({
                "decision_id": str(pos["id"]), "symbol": symbol, "pnl": pnl, "win": pnl > 0,
                "exit_reason": exit_reason,
            })

            if self._record_agent_learning(pos, pnl):
                learned_any = True
                if market_regime != "unknown":
                    regimes_seen.add(market_regime)
            self._record_episodic_memory(pos, pnl, exit_reason)

        if learned_any and len(self.agent_memory.domains()) > 0:
            self.weight_optimizer.propose_weights(evaluation_window=100)
            # Faz 268b — Regime-Aware Learning: global öneriye ek olarak,
            # bu batch'te gerçekten kapanmış işlem gördüğümüz HER rejim
            # için de ayrı bir öneri hesaplanır — bir rejimin snapshot'ı
            # sadece o rejimde gerçek kapanış oldukça güncellenir.
            for regime in regimes_seen:
                self.weight_optimizer.propose_weights(evaluation_window=100, regime=regime)

        return closed
