from datetime import datetime, timedelta
"""Weight Optimizer — Bayesian smoothing ile stabil ağırlık önerisi."""

from enum import Enum

from contracts.agent import VOTING_AGENT_DOMAINS
from contracts.agent_weight_snapshot import AgentWeightSnapshot
from services.agent_memory import AgentMemory, get_reliability_legacy_cutoff
from services.weight_repository import WeightRepository
from contracts.weight_approval import WeightApproval
from database.session_factory import SessionFactory
from database.repositories.weight_approval_repository import WeightApprovalRepository

MAX_WEIGHT_DELTA = 0.10
# Faz 268-sonrası — kullanıcı bulgusu, gerçek olay: reliability_legacy_
# cutoff_at eklendiğinde (kullanıcı isteği: "her ajanın kararda eşit
# ağırlığı olsun") bu, sadece agents/source_reliability_agent.py'ye
# (per-cycle benching) bağlanmıştı — bu, AYRI/kalıcı global ağırlık
# önerisi sistemine hiç yansımamıştı, hâlâ eski/bozuk dönemin tüm
# verisini kullanıyordu. Kesimi buraya da bağlarken İKİNCİ, daha derin
# bir hata bulundu: confidence_factor (min(total/window, 1.0)) az
# taze veriyle küçük çıkınca, smoothed_accuracy (Bayesian prior sayesinde
# veri yokken ~0.5'e yakın, "nötr" bir değer) ile ÇARPILINCA sonuç
# neredeyse sıfıra eziliyordu — "kanıt yok = nötr" değil, "kanıt yok =
# sıfır" davranıyordu. Kesim tarihinden hemen sonra (henüz 500 taze
# kayıt birikmeden) bu, PRATİKTE her ajanı sıfıra çekiyordu. Artık
# yeterli taze (kesim sonrası) kanıt yoksa o domain için hiç değişiklik
# ÖNERİLMİYOR — mevcut ağırlık (varsa) ya da nötr 1.0 aynen korunuyor,
# "kanıtlanana kadar güven" ilkesi (Adaptive Barrier/SourceReliabilityAgent
# ile aynı disiplin).
MIN_SAMPLES_FOR_PROPOSAL = 10


class WeightOptimizer:

    def __init__(
        self,
        agent_memory: AgentMemory,
        weight_repository: WeightRepository | None = None,
        prior_strength: int = 5,
    ):
        self.agent_memory = agent_memory

        self.weight_repository = (
            weight_repository
            if weight_repository
            else WeightRepository()
        )

        self.prior_strength = prior_strength

    @staticmethod
    def _load_proposal_cooldown_hours() -> float:
        """bkz. propose_weights() içindeki Faz 282 notu."""
        try:
            from database.repositories.app_settings_repository import AppSettingsRepository

            with SessionFactory.get_session() as session:
                value = float(AppSettingsRepository(session).get("weight_proposal_cooldown_hours") or 6)
            return value if value >= 0.0 else 6.0
        except Exception as exc:
            import structlog
            structlog.get_logger().warning("weight_proposal_cooldown_hours_load_failed", error=str(exc))
            return 6.0

    def propose_weights(
        self,
        evaluation_window: int = 100,
        regime: str | None = None,
    ) -> AgentWeightSnapshot:
        """Faz 268b — Regime-Aware Learning: regime verilirse, önerilen
        ağırlıklar SADECE o piyasa rejiminde alınmış gerçek kararlardan
        hesaplanır ve o rejime özel bir snapshot olarak saklanır (global
        snapshot'tan bağımsız, ayrı bir onay kuyruğunda). regime=None
        (varsayılan) önceki davranışla birebir aynı — tüm geçmiş, tek
        global snapshot."""

        # Faz 229: savunma katmanı — agent_memory_history/agent_memory.json
        # dosyasında (bu düzeltmeden ÖNCE yazılmış) hâlâ geçersiz domain'ler
        # kalmış olabilir; burada da filtreleniyor.
        domains = [d for d in self.agent_memory.domains() if d in VOTING_AGENT_DOMAINS]

        if not domains:
            return AgentWeightSnapshot(
                weights={},
                evaluation_window=evaluation_window,
                regime=regime,
            )


        # Faz 268g — kullanıcı bulgusu: tek bir evaluation_window'a göre
        # şişirilmiş bir tek sayı, hem "piyasa rejimi hızlı değişiyor, kısa
        # pencere lazım" hem de "kısa pencere gürültüye çok açık, uzun
        # pencere lazım" endişelerinin İKİSİNİ de tek başına çözemiyordu.
        # Artık kısa/orta/uzun vadeli doğruluk AYRI AYRI ölçülüyor (aynı
        # evaluation_window'dan türetilen 3 pencere — varsayılan 100 için
        # 50/100/500) ve nihai ağırlık bunların basit ortalaması: hiçbiri
        # diğerine keyfi bir üstünlük verilmeden ("icat edilmiş" bir
        # ağırlıklandırma değil), ama tek bir pencerenin o anki gürültüsü
        # ya da tek bir rejimin şişirdiği tüm-zamanlar ortalaması artık tek
        # başına belirleyici olamıyor. Her bileşen window_breakdown'da ayrı
        # ayrı görünür kalıyor (şeffaflık, teşhis için).
        windows = {
            "short": max(1, evaluation_window // 2),
            "medium": evaluation_window,
            "long": evaluation_window * 5,
        }

        cutoff = get_reliability_legacy_cutoff()

        # Faz 268b — Regime-Aware Learning: sadece AYNI rejimin (ya da
        # regime=None ise global'in) önceki snapshot'ıyla karşılaştırılır
        # — farklı rejimlerin ağırlıkları elma-armut kıyaslanmaz, ve bir
        # rejimin büyük değişimi başka bir rejimin onay kuyruğunu bloklamaz.
        previous = self.weight_repository.get_latest(regime=regime)
        previous_weights = dict(previous.weights) if previous else {}

        # Faz 282 — kritik bulgu (2026-08-19, kullanıcı: "her işlem
        # kapandığında değişiklik yapıyor sanırım... büyük örneklemlere
        # göre hareket etmesi lazım, her işlem kapandığında bunu yapamaz
        # matematiksel olarak zırva"). has_pending() (aşağıda) sadece O AN
        # bekleyen bir onay olup olmadığını kontrol ediyordu — kullanıcı
        # reddeder etmez (ya da auto_reject_stale ile 1 saat sonra
        # kendiliğinden reddedilince) BİR SONRAKİ kapanış batch'i
        # (dakikalar içinde, aynı küçük veri artışıyla) hemen yeni bir
        # öneri üretebiliyordu. Bu, gerçek soğuma süresi zaten VARSA (ilk
        # öneri değilse) uygulanır — hiç önerisi olmayan bir rejim/global
        # için ilk öneri asla geciktirilmez.
        if previous is not None:
            cooldown_hours = self._load_proposal_cooldown_hours()
            try:
                with SessionFactory.get_session() as session:
                    last_proposed_at = WeightApprovalRepository(session).most_recent_timestamp(regime=regime)
            except Exception as exc:
                import structlog
                structlog.get_logger().warning("weight_proposal_cooldown_check_failed", error=str(exc))
                last_proposed_at = None
            if last_proposed_at is not None and datetime.now() - last_proposed_at < timedelta(hours=cooldown_hours):
                return previous

        # Faz 269-sonrası — kullanıcı bulgusu, gerçek olay: reliability_
        # legacy_cutoff_at set edildikten sadece birkaç gün sonra (bu
        # kesimden bu yana en yoğun ajan bile 500'lük "uzun" pencereyi
        # dolduramamış — 61/500), confidence_factor = min(total/window,
        # 1.0) HER ajanı (kanıtı ne kadar güçlü olursa olsun) aynı
        # ulaşılamaz statik hedefe (500) göre cezalandırıyordu. Gerçek
        # örnek: technical'ın SON 20 kararı %95 isabetliydi ama 61
        # örneklemlik "uzun" penceresi confidence_factor≈%12'ye
        # eziliyordu, önerilen ağırlığı 1.420'den 0.319'a düşürüyordu.
        # Standart düzeltme: her pencerenin hedefi, kesimden bu yana O
        # PENCEREDE GERÇEKTEN birikmiş en yüksek örneklemle (TÜM oy-veren
        # ajanlar arasında) SINIRLANIYOR — icat edilmiş bir sabit değil,
        # "şu ana kadar ne kadar kanıt birikmesi mümkündü" sorusunun
        # doğrudan kendisinden türetiliyor. Kesimden hemen sonra bu,
        # confidence_factor'ü doğal olarak gevşetir (herkes aynı kısa
        # süreye tabi); zaman geçip statik pencereler gerçekten dolmaya
        # başlayınca etkisi kendiliğinden kaybolur (min() zaten statik
        # pencereyi de asla aşmaz).
        summaries: dict[tuple[str, str], object] = {}
        window_ceilings: dict[str, int] = {}
        for label, window in windows.items():
            for d in domains:
                summaries[(d, label)] = self.agent_memory.get_summary(d, window=window, regime=regime, min_timestamp=cutoff)
            window_ceilings[label] = max(
                (summaries[(d, label)].total_predictions for d in domains),
                default=0,
            )
            window_ceilings[label] = max(window_ceilings[label], 1)

        proposed = {}
        window_breakdown: dict[str, dict[str, float]] = {}
        # Kullanıcı bulgusu — gerçek olay: onchain/time/epistemology/
        # relative_strength bir öneride "— (yeni)" diye 1.000'e
        # sıfırlanıyordu, AYNI öneride technical/macro gibi GERÇEK veriye
        # dayanan ajanlar 0.2-0.3'e kesiliyordu — veri eksikliği yüzünden
        # hiç kanıtlanmamış bir ajan, tam da o an aktif olarak
        # değerlendirilip cezalandırılan ajanlardan DAHA GÜVENİLİR
        # görünüyordu. "Veri yok" nötr 1.0 anlamına gelmeli ama "nötr"ün
        # ANLAMI o rundaki GERÇEK verili ajanların ortancasına göre
        # olmalı — sabit 1.0, diğer herkes 1.0'ın altına çekilirken bile
        # değişmiyordu. domains_needing_fallback ilk geçişte toplanır,
        # gerçek veriye dayanan ağırlıkların medyanı hesaplandıktan SONRA
        # (previous_weights önceliği KORUNARAK) çözülür.
        domains_needing_fallback: list[str] = []

        for domain in domains:
            component_scores = {}
            medium_total = 0
            for label, window in windows.items():
                # Faz 263: kritik bulgu — evaluation_window önceden sadece
                # confidence_factor'ü ölçeklendiriyordu, HANGİ kayıtların
                # "doğruluk" sayılacağını asla sınırlamıyordu — ağırlıklar
                # hep tüm-zamanlar ortalamasına göre belirleniyordu, bir
                # ajanın YAKIN ZAMANDA çökmüş olması hiç yansımıyordu (gerçek
                # bulgu: technical_agent tüm-zamanlar %76.7 ama son 20
                # tahmininin %15'i doğru). Artık gerçekten SADECE ilgili
                # pencerenin son N kaydı kullanılıyor.
                #
                # Faz 268-sonrası: reliability_legacy_cutoff_at'ten ÖNCEKİ
                # kayıtlar (eski/bozuk dönem) hiç sayılmıyor — bkz.
                # services/agent_memory.py::get_reliability_legacy_cutoff.
                summary = summaries[(domain, label)]

                total = summary.total_predictions
                if label == "medium":
                    medium_total = total
                correct = int(summary.overall_accuracy * total)

                smoothed_accuracy = (
                    correct + self.prior_strength
                ) / (
                    total + self.prior_strength * 2
                )

                confidence_factor = min(total / window_ceilings[label], 1.0)

                component_scores[label] = round(smoothed_accuracy * confidence_factor, 3)

            window_breakdown[domain] = component_scores

            # Faz 268-sonrası — kritik bulgu: yeterli TAZE (kesim sonrası)
            # kanıt yokken confidence_factor küçük çıkıyor, smoothed_
            # accuracy'nin (veri yokken Bayesian prior sayesinde ~0.5
            # "nötr") ÇARPIMI neredeyse sıfıra eziliyordu — "kanıt yok =
            # nötr" değil, "kanıt yok = sıfır" demek. Kesimden hemen sonra
            # (henüz 500 taze kayıt birikmeden) bu PRATİKTE her ajanı
            # sıfıra çekiyordu. Yeterli kanıt yoksa hiç değişiklik
            # ÖNERİLMİYOR — mevcut ağırlık (varsa) ya da nötr 1.0 aynen
            # korunuyor.
            if medium_total < MIN_SAMPLES_FOR_PROPOSAL:
                if domain in previous_weights:
                    proposed[domain] = previous_weights[domain]
                else:
                    domains_needing_fallback.append(domain)
            else:
                proposed[domain] = round(
                    sum(component_scores.values()) / len(component_scores), 3
                )

        # Kullanıcı bulgusu — bkz. domains_needing_fallback'in üstündeki
        # not: önceki ağırlığı OLMAYAN (gerçekten yeni/hiç veri
        # biriktirememiş) domain'ler artık sabit 1.0 yerine BU RUNDAKİ
        # gerçek verili ağırlıkların medyanına düşüyor — "kanıtlanmamış"
        # olmak, o an aktif değerlendirilen ajanlardan daha güvenilir
        # görünmeyi sağlamamalı. Bu rundaki HİÇBİR domain'de yeterli veri
        # yoksa (aşırı uç durum, ör. sistemin ilk hiç çalışması) son çare
        # olarak 1.0'a düşülür — o zaman gerçekten karşılaştırılacak bir
        # emsal yok.
        #
        # Faz 282 — kritik bulgu (2026-08-19, kullanıcı: "hiçbir mantık
        # kuramadım niye böyle bir teklifte bulunduğuna dair"): gerçek
        # olay — nadir bir rejimde (bullish_high) SADECE technical'ın
        # yeterli örneklemi vardı, diğer 8 ajan fallback'e düştü.
        # "Medyan" TEK elemanlı bir listede matematiksel olarak o TEK
        # değere eşit — sistem farkında olmadan technical'ın kendi
        # skorunu (1.77), hiç kanıtı olmayan 8 ajana AYNEN kopyaladı.
        # Bu, "kanıtlanmamış ajan diğerlerinden güvenilir görünmesin"
        # ilkesinin tam tersi bir yanılsama üretti (sanki 8 ayrı ajan
        # bağımsız olarak AYNI yüksek skora ulaşmış gibi). Medyan artık
        # SADECE gerçekten birden fazla (>=2) veri-güdümlü domain varken
        # kullanılıyor — TEK domain varsa (medyan = o domain'in kendisi,
        # anlamsız bir "konsensüs" izlenimi verir) nötr 1.0'a düşülüyor,
        # HİÇ domain yoksa zaten aynı şekilde 1.0.
        if domains_needing_fallback:
            data_driven_weights = [w for d, w in proposed.items() if d not in domains_needing_fallback]
            if len(data_driven_weights) >= 2:
                fallback = round(sorted(data_driven_weights)[len(data_driven_weights) // 2], 3)
            else:
                fallback = 1.0
            for domain in domains_needing_fallback:
                proposed[domain] = fallback

        snapshot = AgentWeightSnapshot(
            weights=proposed,
            evaluation_window=evaluation_window,
            window_breakdown=window_breakdown,
            previous_snapshot_id=(
                previous.id
                if previous
                else None
            ),
            regime=regime,
        ).finalize()

        # Faz 214: kritik bulgu — bu metod optimize()'daki (aynı sınıfın
        # diğer ağırlık güncelleme yolu) >%10 değişiklik için insan onayı
        # zorunluluğunu (WeightApproval, Faz 160-165) hiç uygulamıyordu,
        # doğrudan kaydediyordu. services/position_closer.py (Faz 210b/211b)
        # gerçek kapanan her işlemde bunu çağırınca, büyük ağırlık
        # sıçramaları hiç insan gözünden geçmeden canlıya uygulanmaya
        # başladı — kasıtlı güvenlik kontrolünü fark etmeden atlıyordu.
        if previous_weights:
            max_change = max(
                abs(proposed.get(k, 0) - previous_weights.get(k, 0))
                for k in set(proposed) | set(previous_weights)
            )
            if max_change > MAX_WEIGHT_DELTA:
                try:
                    with SessionFactory.get_session() as session:
                        repo = WeightApprovalRepository(session)
                        # Faz 229: kritik bulgu — bekleyen bir onay ZATEN
                        # varsa yenisini eklemiyoruz. Bu kontrol yoksa her
                        # çağrıda (gerçek her pozisyon kapanışında) aynı
                        # büyük fark yeniden hesaplanıp KOŞULSUZCA yeni bir
                        # satır ekleniyordu — üretimde 7000'den fazla
                        # neredeyse aynı bekleyen onay birikti.
                        if repo.has_pending(regime=regime):
                            return previous
                        approval = WeightApproval(
                            expires_at=datetime.now() + timedelta(hours=24),
                            proposed_weights=proposed,
                            previous_weights=previous_weights,
                            max_delta=MAX_WEIGHT_DELTA,
                            regime=regime,
                            status="pending",
                        )
                        repo.save(approval)
                    return previous  # onaylanana kadar mevcut snapshot geçerli
                except Exception as e:
                    import structlog
                    logger = structlog.get_logger()
                    logger.error('weight_approval_save_failed', error=str(e), max_change=max_change)
                    # Tablo henüz yoksa (ör. eski migration) eskisi gibi
                    # doğrudan kaydetmeye düş — sessizce hiçbir şeyin
                    # güncellenmemesi daha kötü.

        self.weight_repository.save(snapshot)

        return snapshot

    def optimize(
        self,
        agents: list[dict],
        outcome,
        executed_direction: str = "",
        require_approval: bool = True,
    ) -> dict[str, float]:
        """
        Feedback-loop weight update with a gradual delta cap.
        Large changes (>5%) require human approval.

        Faz 234: kritik bulgu — canlıda doğrulandı: bir pending approval'da
        9 ajanın HEPSİNE tıpatıp aynı +0.100 (MAX_WEIGHT_DELTA'nın tavanı)
        verilmişti. Kök neden: `decision_score` (tüm cycle'ın TEK, genel
        sonucu — Faz 211b'de position_closer.py'de aynı hatanın kardeşi)
        her katılan ajana FARKLILAŞTIRILMADAN bloke uygulanıyordu — ajanın
        kendi yönü nihai kararla aynı mıydı, ters miydi hiç bakılmıyordu.
        Sonuç: gerçek "hangi ajan iyi/kötü" öğrenmesi değil, sadece son
        cycle kârlıysa TÜM ağırlıkları birlikte şişiriyordu (kayıpta da
        birlikte söndürüyordu). position_closer.py::_record_agent_learning()
        (Faz 211b) zaten doğru deseni kullanıyor — aynısı burada uygulandı:
        ajan nihai yönle AYNI yöndeyse decision_score'un kendisi, TERS
        yöndeyse (ya da nihai bir yön varken WAIT dediyse) decision_score'un
        TERSİ kullanılıyor.
        """
        current_snapshot = self.weight_repository.get_latest()
        current_weights = dict(current_snapshot.weights) if current_snapshot else {}

        decision_score = getattr(outcome, "decision_score", 0.0)
        executed = (executed_direction or "").upper()

        new_weights = {}
        adjusted_domains = set()

        for agent in agents:
            domain = self._normalize_domain(agent)
            if not domain:
                continue

            adjusted_domains.add(domain)
            old_weight = current_weights.get(domain, 1.0)

            agent_direction = str(
                agent.get("direction") if isinstance(agent, dict) else getattr(agent, "direction", "")
            ).upper()
            agent_score = decision_score if agent_direction == executed else -decision_score

            desired = old_weight + (agent_score * 0.2)
            desired = max(0.0, min(2.0, desired))

            new_weights[domain] = self._clip_delta(old_weight, desired)

        for domain, weight in current_weights.items():
            if domain not in new_weights:
                new_weights[domain] = weight

        # Approval gate: >5% max change requires human approval
        if current_weights and new_weights:
            max_change = max(
                abs(new_weights.get(k, 0) - current_weights.get(k, 0))
                for k in set(new_weights) | set(current_weights)
            )
            if require_approval and max_change > 0.05:
                try:
                    with SessionFactory.get_session() as session:
                        repo = WeightApprovalRepository(session)
                        # Faz 229: aynı dedup kontrolü — bu metod her gerçek
                        # trading cycle'da çağrıldığı için (optimize(),
                        # propose_weights()'ten çok daha sık) dedup kontrolü
                        # burada daha da kritik.
                        if repo.has_pending():
                            return current_weights
                        approval = WeightApproval(
                            expires_at=datetime.now() + timedelta(hours=24),
                            proposed_weights=new_weights,
                            previous_weights=current_weights,
                            max_delta=MAX_WEIGHT_DELTA,
                            status="pending",
                        )
                        repo.save(approval)
                    return current_weights  # Return old weights until approved
                except Exception as e:
                    import structlog
                    logger = structlog.get_logger()
                    logger.error('weight_approval_save_failed', error=str(e), max_change=max_change)
                    pass  # Table may not exist yet — fall through to allow weight update

        return new_weights

    def _clip_delta(self, old_weight: float, new_weight: float) -> float:
        delta = new_weight - old_weight
        if abs(delta) > MAX_WEIGHT_DELTA:
            return old_weight + (MAX_WEIGHT_DELTA * (1 if delta > 0 else -1))
        return new_weight

    @staticmethod
    def _normalize_domain(agent) -> str | None:
        # Pydantic model veya dict olabilir
        if hasattr(agent, "model_dump"):
            data = agent.model_dump()
        elif hasattr(agent, "dict"):
            data = agent.dict()
        elif isinstance(agent, dict):
            data = agent
        else:
            data = {}

        domain = data.get("domain") or data.get("agent_id")
        if isinstance(domain, Enum):
            domain = domain.value
        if isinstance(domain, dict):
            domain = domain.get("value")
        domain = str(domain).lower() if domain is not None else None

        # Faz 229: kritik bulgu — burası önceden domain eksikse ya da
        # (agent_id gibi) gerçek bir domain adı olmayan bir şeye düşerse
        # sessizce "unknown" döndürüyordu — WeightOptimizer bu sahte domain
        # için de bir ağırlık önerip insan onay ekranını kirletiyordu
        # (canlı üretimde doğrulandı: "unknown" diye bir satır gerçekten
        # oluşmuştu). Artık gerçek 9 oy-veren ajandan biri değilse None
        # dönüyor, çağıran zaten `if not domain: continue` ile atlıyor.
        if domain not in VOTING_AGENT_DOMAINS:
            return None
        return domain