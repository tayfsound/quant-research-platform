"""Faz 352 — Regime Reversal Guardian, saf (pure) hesaplama katmanı.

Kullanıcı fikri (2026-08-22), GERÇEK, o anda yaşanan bir olayla
doğrulandı: LONG'da art arda 14 stop-loss (birbirinden bağımsız birçok
sembolde, ~2 saatlik bir pencerede), aynı anda 275 açık LONG'un 170'i
zararda. Kill switch'in GLOBAL ardışık-kayıp sayacının (services/
risk_state.py) YÖN-bazlı, "sadece kayıp" değil "sadece stop-loss ile
çıkış" (kasıtlı olarak daha spesifik — manuel/breakeven/time_expired
çıkışlar bir rejim değişikliği sinyali DEĞİL, planlı bir risk seviyesinin
GERÇEKTEN aşıldığını gösteren SADECE stop-loss) karşılığı."""


def consecutive_stop_streak(trades_desc: list[dict]) -> int:
    """trades_desc: TEK bir yön için, en yeniden en eskiye sıralı, her
    biri 'outcome' (dict, 'exit_reason' alanı) içeren GERÇEK kapanmış
    işlemler. En son işlemden geriye doğru, ilk stop-loss OLMAYAN
    kapanışa kadar ardışık stop-loss sayısını döner. Boş listede/ilk
    işlem stop değilse 0 — icat edilmiş bir streak asla üretilmez."""
    streak = 0
    for t in trades_desc:
        exit_reason = (t.get("outcome") or {}).get("exit_reason")
        if exit_reason == "stop_loss":
            streak += 1
        else:
            break
    return streak
