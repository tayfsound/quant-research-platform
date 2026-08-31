"""Decision Fusion — Expected Value ve Risk/Reward odaklı son karar aşaması."""
from contracts.belief import Belief
from contracts.context import CognitiveCycleContext
from contracts.contexts.decision import ActionType
from services.confidence_calibration import calibrate_confidence, get_calibration_curve_for_symbol
from services.inner_critic import InnerCritic

# Faz 328 — kullanıcı isteği: Opportunity Quality (Grup B, ölçüm-only)
# modülü canlıya alındı — bu, kullanıcının bu oturumda onayladığı ilk
# Grup B->karar-hattı wiring'i. Gerçek veriyle ölçüldü (services/
# opportunity_quality_gatherer.py, 1410 gerçek kapanmış işlem, pump_fade
# hariç): council'in 9 ajan oyu arasındaki anlaşma (Shannon entropi
# tabanlı, analytics/opportunity_quality.py::compute_agent_agreement)
# "low" (<0.34) kovasındayken kazanma oranı %64.0 (n=1033, sağlam),
# "medium" (0.34-0.67) kovasındayken %93.0 (n=370, sağlam) — 29 puanlık
# gerçek fark. "high" (>=0.67) kovası %100 ama n=7 — quant_agent'ın
# "disagree" kovasıyla AYNI ilke: istatistiksel olarak yetersiz, ona
# dokunulmuyor. SADECE "low" kovası, gerçek/sağlam kanıtlı (medium'a
# göre) ölçülen orana (%64.0/%93.0 ≈ 0.6883) göre indiriliyor —
# quant_agent'ın trend-uyum indirimiyle AYNI desen (sadece kötü kova
# indirilir, iyi kova asla büyütülmez).
_OPPORTUNITY_QUALITY_LOW_AGREEMENT_DISCOUNT = 0.6883


def compute_fused_confidence(
    ctx: CognitiveCycleContext,
    belief: Belief | None = None,
    opinions: list | None = None,
) -> float:
    """DecisionFusion.evaluate()'in confidence hesaplama kısmının YAN
    ETKİSİZ hali (ctx'i mutate etmez, relevant_knowledge'a yazmaz) —
    kalibrasyon eğrisi + opportunity-quality düşük-anlaşma indirimi +
    InnerCritic çarpanının BİRLEŞİK sonucu.

    Faz 363 — kullanıcı bulgusu/isteği: RiskTargetStage, Meta-Label
    Model'e "confidence" özelliği verirken bu fonksiyon YERİNE doğrudan
    `ctx.decision.confidence`'ı okuyordu — pipeline'da DecisionFusion'dan
    ÖNCE çalıştığı için (bkz. cognitive_engine.py::run sırası) bu ham,
    henüz kalibre/indirim GÖRMEMİŞ bir değerdi. Ama modelin EĞİTİM verisi
    (decisions.confidence sütunu) decision_fusion SONRASI, yani bu
    fonksiyonun ürettiği NİHAİ değerdi — train/serve tutarsızlığı.
    RiskTargetStage artık AYNI bu fonksiyonu çağırıyor, eğitim ve
    çalışma zamanı artık aynı anlamdaki confidence'ı görüyor."""
    raw_confidence = ctx.decision.confidence or (belief.strength if belief else 0.0)
    # Faz 248: kritik bulgu — gerçek veriyle ölçüldü, beyan edilen
    # confidence sistemli olarak şişirilmiş (%40-60 aralığında gerçek
    # kazanma oranı 20-24 puan daha düşük). EV hesabı ham confidence
    # yerine gerçek geçmiş kararlardan çıkarılan ampirik kalibrasyon
    # eğrisinden geçirilmiş halini kullanıyor — yeterli veri yoksa
    # (fail-closed) ham değer değişmeden kalıyor.
    # Faz 325 — kullanıcı bulgusu: kripto içi büyük-cap/küçük-cap
    # ayrımı gerçek veriyle ölçüldü (35 puanlık fark, bkz. services/
    # confidence_calibration.py::compute_market_cap_tier_calibration_
    # curves üstündeki not) — symbol verilirse önce o eğriye bakılır,
    # yeterli veri yoksa (fail-closed) tek küresel eğriye düşülür.
    curve = get_calibration_curve_for_symbol(ctx.market.symbol)
    confidence = calibrate_confidence(raw_confidence, curve=curve)

    # Faz 328 — bkz. _OPPORTUNITY_QUALITY_LOW_AGREEMENT_DISCOUNT
    # üstündeki yorum. opinions verilmezse (ör. eski/izole testler)
    # hiçbir şey değişmez — fail-closed.
    if opinions:
        from analytics.opportunity_quality import compute_agent_agreement

        votes = {"LONG": 0, "SHORT": 0, "WAIT": 0}
        for o in opinions:
            direction = (getattr(o, "direction", "") or "").upper()
            if direction in votes:
                votes[direction] += 1
        agreement = compute_agent_agreement(votes)
        if agreement < 0.34:
            confidence *= _OPPORTUNITY_QUALITY_LOW_AGREEMENT_DISCOUNT

    # Faz 268-sonrası — kritik bulgu (üçüncü taraf inceleme + kod
    # doğrulaması): InnerCritic instantiate ediliyordu ama .review()
    # hiç çağrılmıyordu — ürettiği risk_flags/objections tamamen ölü
    # koddu. Artık gerçekten çağrılıyor ve iki sayısal çıktısı
    # (bkz. inner_critic.py) confidence/final_size'ı GERÇEKTEN
    # etkiliyor, sadece açıklanabilirlik için loglanmıyor.
    critique = InnerCritic().review(ctx)
    confidence *= critique["confidence_multiplier"]
    return confidence


class DecisionFusion:
    def __init__(self):
        self.critic = InnerCritic()

    def evaluate(
        self,
        ctx: CognitiveCycleContext,
        belief: Belief | None = None,
        opinions: list | None = None,
    ) -> CognitiveCycleContext:
        confidence = compute_fused_confidence(ctx, belief, opinions)

        # Aşağıdaki iki blok SADECE açıklanabilirlik/loglama için —
        # compute_fused_confidence() zaten yukarıda bu hesabı yaptı, burada
        # AYNI mantığı (agreement/critique) TEKRAR çalıştırıp
        # relevant_knowledge'a kaydediyoruz (yan etkisiz, deterministik,
        # tekrar hesaplamanın maliyeti önemsiz).
        if opinions:
            from analytics.opportunity_quality import compute_agent_agreement

            votes = {"LONG": 0, "SHORT": 0, "WAIT": 0}
            for o in opinions:
                direction = (getattr(o, "direction", "") or "").upper()
                if direction in votes:
                    votes[direction] += 1
            agreement = compute_agent_agreement(votes)
            if agreement < 0.34:
                ctx.cognition.relevant_knowledge.append({
                    "type": "opportunity_quality",
                    "data": {
                        "agent_agreement": round(agreement, 4),
                        "bucket": "low",
                        "reason": "Düşük ajan anlaşması — geçmiş veride bu kova düşük isabetle ilişkili "
                                  "(n=1033, %64.0 kazanma vs medium kovada %93.0), confidence indirildi",
                    },
                })

        critique = self.critic.review(ctx)
        if critique["risk_flags"] or critique["objections"]:
            ctx.cognition.relevant_knowledge.append({
                "type": "inner_critic",
                "data": critique,
            })

        # Kritik bulgu (Faz 328 sırasında bulundu): buraya kadar hesaplanan
        # confidence (kalibrasyon + cap-tier eğrisi + opportunity quality
        # indirimi + InnerCritic çarpanı) SADECE aşağıdaki yerel EV
        # hesabında kullanılıyordu, ctx.decision.confidence'a hiç geri
        # yazılmıyordu — persist edilen/downstream tüketen (Kelly boyutlama,
        # dashboard, decisions.confidence sütunu) hep ham/kalibre-edilmemiş
        # değeri görüyordu. Artık burada geri yazılıyor ki EV kapısından
        # geçen (veya geçmeyen) gerçek karar, gösterilen/kaydedilen
        # confidence ile tutarlı olsun.
        ctx.decision.confidence = round(confidence, 4)

        win = ctx.decision.take_profit_distance or 0.0
        loss = abs(ctx.decision.stop_loss_distance or 0.0)
        ev = confidence * win - (1 - confidence) * loss

        if ev <= 0:
            # Faz 372 — SHORT Exploration deneyi (kullanıcı tasarımı,
            # 2026-08-29): analytics/mae_mfe.py iki bağımsız ölçümde
            # SHORT'un gerçek bir kenarı olmadığını gösterdi, ama BU KAPI
            # SHORT'u sürekli reddettiği için yeni outcome verisi hiç
            # birikemiyor — klasik exploration/exploitation kilidi. Global
            # EV kapısı BURADA DEĞİŞMİYOR (normal SHORT/LONG davranışı
            # birebir aynı) — sadece, TP/SL'i GERÇEKTEN hesaplanmış
            # (win>0 veya loss>0 — MetaStage zaten WAIT dediyse RiskTargetStage
            # hiç çalışmamış olur, o durumda exploration da anlamsız),
            # dinamik üst-yüzdelikte (P85) confidence'a sahip, sıkı hard-
            # cap'li (eşzamanlı/haftalık/sembol-cooldown/kendi kill switch'i
            # — bkz. services/short_exploration.py) bir SHORT adayı için
            # AYRI, izole, çok küçük boyutlu bir "keşif" penceresi açılıyor.
            # experiment_bucket=short_exploration_v1 ile TAM izole —
            # decision_recorder.py'nin "experiment_bucket is None" şartlı
            # TÜM post-hoc gate'leri bu kovayı hiç görmez, saf bir örneklem
            # kalır (normal model performans istatistiklerine karışmaz).
            direction = (ctx.decision.proposed_direction or "").upper()
            explored = False
            if direction == "SHORT" and (win > 0 or loss > 0):
                from services.short_exploration import (
                    EXPERIMENT_BUCKET as _SHORT_EXPLORATION_BUCKET,
                )
                from services.short_exploration import (
                    SIZE_MULTIPLIER as _SHORT_EXPLORATION_SIZE_MULTIPLIER,
                )
                from services.short_exploration import is_eligible as _short_exploration_is_eligible

                eligible, reason = _short_exploration_is_eligible(ctx.market.symbol or "", confidence)
                if eligible:
                    explored = True
                    ctx.decision.action = ActionType.ENTER_SHORT
                    ctx.decision.final_size = abs(ctx.decision.proposed_size) * _SHORT_EXPLORATION_SIZE_MULTIPLIER
                    ctx.cognition.relevant_knowledge.append({
                        "type": "experiment_bucket",
                        "data": {"bucket": _SHORT_EXPLORATION_BUCKET},
                    })
                    ctx.cognition.relevant_knowledge.append({
                        "type": "decision_fusion",
                        "data": {
                            "adjustment": "SHORT exploration — EV negatif ama kontrollü keşif penceresinden geçti",
                            "predicted_ev": round(ev, 6),
                            "confidence": round(confidence, 4),
                        },
                    })
                else:
                    ctx.cognition.relevant_knowledge.append({
                        "type": "decision_fusion",
                        "data": {
                            "rejection": "Negatif beklenen değer (EV)", "ev": round(ev, 6),
                            "confidence": round(confidence, 4), "win": round(win, 6), "loss": round(loss, 6),
                            "short_exploration_rejected_reason": reason,
                        },
                    })
            if not explored:
                ctx.decision.action = ActionType.WAIT
                ctx.decision.final_size = 0.0
                if direction != "SHORT" or not (win > 0 or loss > 0):
                    # Faz 380 — teşhis: kullanıcı bulgusu ("el çok sıkı,
                    # canlıda hiç açmamış") — win/loss/confidence olmadan
                    # sadece "ev" görmek, hangi bileşenin EV'yi negatife
                    # çektiğini (düşük confidence mi, dar hedef mi, geniş
                    # stop mu) ayırt etmeyi imkansız kılıyordu. Geçici DEĞİL
                    # — decision decomposition ekranındaki AYNI ilke
                    # (Faz 376), kalıcı bir teşhis alanı.
                    ctx.cognition.relevant_knowledge.append({
                        "type": "decision_fusion",
                        "data": {
                            "rejection": "Negatif beklenen değer (EV)", "ev": round(ev, 6),
                            "confidence": round(confidence, 4), "win": round(win, 6), "loss": round(loss, 6),
                        },
                    })
                return ctx

        # Faz 391 — kullanıcı isteği: min_profit_target_pct kaldırıldı.
        # SL/TP artık dinamik/otomatik (Adaptive Barrier Engine + TP/SL
        # Confluence + min_stop_pct tabanı) belirlendiği için bu statik
        # komisyon-tabanı kontrolü (Faz 210) redundant hale geldi —
        # min_stop_pct tabanı zaten hedefleri orantılı geniş tutuyor.

        if critique["size_multiplier"] < 1.0:
            ctx.decision.final_size *= critique["size_multiplier"]
            ctx.cognition.relevant_knowledge.append({
                "type": "decision_fusion",
                "data": {
                    "adjustment": "İç Eleştirmen (InnerCritic) pozisyon boyutunu küçülttü",
                    "size_multiplier": critique["size_multiplier"],
                    "risk_flags": critique["risk_flags"],
                },
            })

        if loss > 0 and win / loss < 0.5:
            ctx.decision.final_size *= 0.5
            ctx.cognition.relevant_knowledge.append({
                "type": "decision_fusion",
                "data": {
                    "adjustment": "Risk/ödül oranı çok düşük, boyut yarıya indirildi",
                    "rr": round(win / loss, 6),
                },
            })

        return ctx
