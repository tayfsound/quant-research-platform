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
from services.weight_optimizer import WeightOptimizer
from services.weight_repository import WeightRepository
from simulator.fee_engine import FeeEngine

# Faz 229: artık contracts/agent.py::VOTING_AGENT_DOMAINS — tek gerçek
# kaynak, services/learning_loop.py ve services/weight_optimizer.py da
# aynısını kullanıyor (bkz. o dosyalardaki "unknown" domain sızıntısı bulgusu).
_VALID_AGENT_DOMAINS = VOTING_AGENT_DOMAINS

logger = structlog.get_logger()


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

    def _age_seconds(self, opened_at: datetime, now: datetime) -> float:
        # Bilinen borç (CURRENT_STATE.md'de dokümante): DB'de naive/aware
        # datetime karışık olabilir. Burada ikisini de kabul ediyoruz.
        if opened_at.tzinfo is None:
            return (now.replace(tzinfo=None) - opened_at).total_seconds()
        return (now - opened_at).total_seconds()

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
        yansıtıyor."""
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
        market_regime = "unknown"
        for item in contributions:
            if isinstance(item, dict) and item.get("type") == "market_snapshot":
                features = ((item.get("data") or {}).get("features")) or {}
                market_regime = features.get("trend", "unknown")
                break

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
            ))
            recorded = True

        return recorded

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
        return gross_pnl - fee

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
        pnl = gross_pnl - fee
        now = datetime.now(UTC)

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
            )
            self._record_agent_learning(pos, pnl)
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

        for pos in decision_repo.list_open_positions():
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
            pnl = gross_pnl - fee

            decision_repo.close_position(
                decision_id=str(pos["id"]),
                exit_price=exit_price,
                pnl=pnl,
                closed_at=now,
                outcome={
                    "pnl": pnl,
                    "gross_pnl": gross_pnl,
                    "fee": fee,
                    "win": pnl > 0,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "quantity": quantity,
                    "hold_seconds": age,
                    "exit_reason": exit_reason,
                },
            )
            closed.append({
                "decision_id": str(pos["id"]), "symbol": symbol, "pnl": pnl, "win": pnl > 0,
                "exit_reason": exit_reason,
            })

            if self._record_agent_learning(pos, pnl):
                learned_any = True

        if learned_any and len(self.agent_memory.domains()) > 0:
            self.weight_optimizer.propose_weights(evaluation_window=100)

        return closed
