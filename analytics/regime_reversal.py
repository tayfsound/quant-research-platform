"""Faz 352 — Regime Reversal Guardian, saf (pure) hesaplama katmanı.

Kullanıcı fikri (2026-08-22), GERÇEK, o anda yaşanan bir olayla
doğrulandı: LONG'da art arda 14 stop-loss (birbirinden bağımsız birçok
sembolde, ~2 saatlik bir pencerede), aynı anda 275 açık LONG'un 170'i
zararda. Kill switch'in GLOBAL ardışık-kayıp sayacının (services/
risk_state.py) YÖN-bazlı, "sadece kayıp" değil "sadece GERÇEK, kontrolsüz
kayıpla çıkış" (kasıtlı olarak daha spesifik — manuel/time_expired
çıkışlar bir rejim değişikliği sinyali DEĞİL, planlı/kontrollü bir çıkış)
karşılığı.

Faz 363 — kritik bulgu, gerçek veriyle doğrulandı: streak hesabı ÖNCEDEN
SADECE exit_reason=='stop_loss'ı sayıyordu — 'liquidation' (kaldıraçlı
bir pozisyonun zorla, GENELDE stop_loss'tan bile daha büyük bir kayıpla
kapanması, "kontrolsüz kayıp" tanımına stop_loss'tan DAHA FAZLA uyan bir
sonuç) FARKLI bir etiket taşıdığı için streak'i KIRIYORDU, ondan ÖNCEKİ
(daha eski) ardışık stop_loss'ları bile saymadan durduruyordu. Canlıda
yakalandı (2026-08-26): son 20 LONG kapanışının TAMAMI kayıptı (stop_loss
+liquidation karışık) ama eski kod SADECE 6 streak buluyordu (7. sıradaki
bir liquidation streak'i kesiyordu) — guardian'ın eşiği (10) hiç aşılmadı,
22 Ağustos'ta doğrulanan koruma bu sefer HİÇ tetiklenmedi. Artık analytics/
failure_classifier.py::LOSS_EXIT_REASONS ile AYNI, tutarlı "gerçek kayıp"
tanımını kullanıyor (stop_loss/breakeven_stop/liquidation/reduced_loss_
stop) — manuel/time_expired hâlâ HARİÇ (bunlar gerçekten planlı/kontrollü
çıkışlar, rejim sinyali değil)."""

from analytics.failure_classifier import LOSS_EXIT_REASONS


def consecutive_stop_streak(trades_desc: list[dict]) -> int:
    """trades_desc: TEK bir yön için, en yeniden en eskiye sıralı, her
    biri 'outcome' (dict, 'exit_reason' alanı) içeren GERÇEK kapanmış
    işlemler. En son işlemden geriye doğru, ilk GERÇEK-KAYIP-OLMAYAN
    kapanışa kadar ardışık kayıp sayısını döner (bkz. modül dokümanındaki
    LOSS_EXIT_REASONS gerekçesi). Boş listede/ilk işlem kayıp değilse 0 —
    icat edilmiş bir streak asla üretilmez."""
    streak = 0
    for t in trades_desc:
        exit_reason = (t.get("outcome") or {}).get("exit_reason")
        if exit_reason in LOSS_EXIT_REASONS:
            streak += 1
        else:
            break
    return streak
