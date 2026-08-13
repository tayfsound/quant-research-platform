"""Economic Calendar Integration — FOMC toplantıları ve CPI yayın
tarihleri. fred_provider.py'nin GERİYE dönük trend verisinden farklı: bu
modül İLERİYE dönük, GERÇEK ve resmi olarak duyurulmuş takvim tarihlerini
kullanıyor:
- FOMC: federalreserve.gov/monetarypolicy/fomccalendars.htm (2026-08-13'te
  WebFetch ile doğrulandı).
- CPI: usinflationcalculator.com/inflation/consumer-price-index-release-
  schedule (BLS'in kendi resmi takvimine dayanıyor, 2026-08-13'te
  doğrulandı; bls.gov'un kendi sayfası WebFetch'e 403 döndürdüğü için
  ikincil ama BLS verisini birebir yansıtan bir kaynak kullanıldı).

Yüksek etkili bir makro yayının hemen öncesinde piyasa genelde anormal
derecede volatil olur ve mevcut sinyaller (technical/order_flow)
güvenilirliğini kaybedebilir — bu YENİ bir strateji değil, kurumsal risk
yönetiminde standart bir uygulama (event risk).

Tarihler MANUEL olarak güncellenmiş sabitler — otomatik, ücretsiz ve
güvenilir bir takvim API'si bulunamadı. FOMC toplantıları bir önceki yıl
sonunda resmen açıklanır, CPI tarihleri de BLS tarafından yıl başında ilan
edilir; bu listenin yılda 1-2 kez elle güncellenmesi gerekiyor (bkz.
_LAST_VERIFIED_AT) — süresi geçmiş bir listeden asla "olay yok" yerine
sessizce yanlış bir "olay yok" sonucu üretilmiyor, sadece o tarihten
sonrası için liste boş kalır (fail-closed: gelecekte hiç olay
göremezsiniz, ama olmayan bir olay asla İCAT edilmez)."""
from datetime import UTC, date, datetime

_LAST_VERIFIED_AT = "2026-08-13"

# İki günlük FOMC toplantılarının İKİNCİ (karar açıklanan) günü.
FOMC_DECISION_DATES = [
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17),
    date(2026, 7, 29), date(2026, 9, 16), date(2026, 10, 28), date(2026, 12, 9),
    date(2027, 1, 27), date(2027, 3, 17), date(2027, 4, 28), date(2027, 6, 9),
    date(2027, 7, 28), date(2027, 9, 15), date(2027, 10, 27), date(2027, 12, 8),
]

CPI_RELEASE_DATES = [
    date(2026, 1, 13), date(2026, 2, 13), date(2026, 3, 11), date(2026, 4, 10),
    date(2026, 5, 12), date(2026, 6, 10), date(2026, 7, 14), date(2026, 8, 12),
    date(2026, 9, 11), date(2026, 10, 14), date(2026, 11, 10), date(2026, 12, 10),
]

# FOMC kararı genelde 14:00 ET (=18:00 UTC kışın/yazın DST farkına göre
# ~1 saat kayabilir — bu düzeyde bir hassasiyet event-proximity riski için
# gerekli değil). CPI genelde 08:30 ET (=12:30 UTC).
_FOMC_ANNOUNCEMENT_UTC_HOUR = 18
_CPI_ANNOUNCEMENT_UTC_HOUR = 12
HIGH_IMPACT_WINDOW_HOURS = 24


def get_upcoming_events(as_of: datetime, lookahead_hours: int = 48) -> list[dict]:
    """as_of'tan itibaren lookahead_hours içindeki GERÇEK (resmi takvim)
    FOMC/CPI olaylarını, en yakından en uzağa sıralı döner. Geçmiş
    tarihler ya da lookahead penceresinin dışındakiler dönmez."""
    events = []
    for d in FOMC_DECISION_DATES:
        event_dt = datetime(d.year, d.month, d.day, _FOMC_ANNOUNCEMENT_UTC_HOUR, 0, tzinfo=UTC)
        hours_until = (event_dt - as_of).total_seconds() / 3600
        if 0 <= hours_until <= lookahead_hours:
            events.append({"type": "fomc", "date": d.isoformat(), "hours_until": round(hours_until, 1)})
    for d in CPI_RELEASE_DATES:
        event_dt = datetime(d.year, d.month, d.day, _CPI_ANNOUNCEMENT_UTC_HOUR, 30, tzinfo=UTC)
        hours_until = (event_dt - as_of).total_seconds() / 3600
        if 0 <= hours_until <= lookahead_hours:
            events.append({"type": "cpi", "date": d.isoformat(), "hours_until": round(hours_until, 1)})
    return sorted(events, key=lambda e: e["hours_until"])


def compute_event_proximity(as_of: datetime, high_impact_window_hours: int = HIGH_IMPACT_WINDOW_HOURS) -> dict:
    """Yüksek etkili bir yayın high_impact_window_hours içinde mi?
    epistemology_agent.py'nin data_quality_score kontrolüyle AYNI desende
    kullanılan basit bir bayrak+detay."""
    upcoming = get_upcoming_events(as_of, lookahead_hours=high_impact_window_hours)
    return {
        "high_impact_event_imminent": len(upcoming) > 0,
        "next_events": upcoming,
    }
