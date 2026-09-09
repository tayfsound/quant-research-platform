"""Örüntü Hayatta Kalma Analizi — Faz 471 (2026-09-09).

Dış incelemenin (kullanıcı paylaştı) tek gerçekten YENİ önerisi buydu:

    Pattern A: ilk WR %89, N=27
    sonraki 50 örnek  -> %82
    sonraki 100       -> %79
    sonraki 200       -> %76
    Bu pattern hâlâ yaşıyor mu, yoksa 89 -> 72 -> 59 -> 51 diye eriyor mu?
    "Gerçek edge ile backtest anomalisi arasındaki fark burada."

Doğru bir gözlem — ama örnekteki YÖNTEMDE bir kusur var ve bu modül onu
düzeltiyor: **ham WR düşüşü tek başına çürüme kanıtı değildir.** 89'dan
76'ya iniş, örüntü aynı gücünü korurken PİYASANIN değişmesinden de
gelebilir (bugün defalarca gördük: `rsi_percentile` ham −0,175 iken
sembol-içi +0,000; onchain özellikleri piyasa-geneli çıktı).

Bu yüzden burada her pencerede örüntünün WR'ı, O PENCERENİN KENDİ
taban oranıyla karşılaştırılıyor:

    excess(pencere) = örüntü_WR(pencere) − POPÜLASYONUN GERİ KALANI(pencere)

Taban, örüntünün KENDİ kayıtlarını DIŞLIYOR. Sebep bir testte ortaya
çıktı: taban örüntüyü de içerirse, örüntü popülasyonun büyük bir payını
oluşturduğunda kendi tabanını yukarı çekip fazlalığı seyreltiyor (payı
%50 ise fazlalık yarıya iniyor). Dışlayınca ölçüm "bu örüntü geri
kalandan iyi mi" sorusuna dönüyor ve örüntünün payından BAĞIMSIZ
oluyor — rejimler arası karşılaştırma da ancak böyle anlamlı.

Hayatta kalma sorusu "WR düştü mü" değil, **"taban üstü fazlalık
korunuyor mu"**. Yükselen bir piyasada %76, taban %72 ise örüntü hâlâ
yaşıyordur; taban %78 ise ölmüştür.

Ayrıca `consistent_chunks` (fazlalığın kaç pencerede pozitif kaldığı)
raporlanıyor — Faz 458/463'ün günlük tutarlılık disiplininin aynısı:
tek bir iyi pencere kanıt değildir.

REJİM KIRILIMI (kullanıcı isteği: "Ölçtüğümüz her şeyi rejime göre
değerlendirmemiz lazım; hangi rejimde hangi verinin anlamlı olduğunu
anlayamayız yoksa."): bir örüntü `bullish_normal`'da yaşarken
`bearish_low`'da çökmüş olabilir ve havuzlanmış tek bir sayı bunu
gizler. Her örüntü için `by_regime` kırılımı da veriliyor — orada da
taban O REJİMİN kendi taban oranı, yani rejimler arası zorluk farkı
fazlalıktan düşüyor.

Kasıtlı olarak SADECE ölçüm — hiçbir örüntüyü otomatik aktive/pasifize
etmiyor.
"""
MIN_PER_CHUNK = 15
# Rejim kırılımı zorunlu olarak daha ince; havuzlanmış eşikle aynı
# olamaz ama gürültüyü de kabul edemeyiz.
MIN_PER_REGIME = 30
DEFAULT_CHUNK_SIZE = 100
# Fazlalığın "hâlâ var" sayılması için gereken alt sınır. Keyfi olduğu
# açıkça belirtiliyor; Faz 463/467'deki NEUTRAL_BAND ile aynı büyüklük.
SURVIVAL_BAND = 0.02


def _win_rate(members: list[dict]) -> float:
    return sum(1 for r in members if r["won"]) / len(members)


def compute_pattern_survival(
    records: list[dict],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    min_per_chunk: int = MIN_PER_CHUNK,
) -> dict | None:
    """records: [{"patterns": list[str], "won": bool, "timestamp": ...,
                  "regime": str | None}, ...]
    — TÜM kararlar/işlemler (sadece örüntüye ait olanlar değil). `patterns`
    o kaydın ait olduğu örüntü hücrelerinin listesi; boş olabilir. Taban
    oranı her pencerede TÜM kayıtlardan hesaplanır, bu yüzden popülasyonun
    tamamı gerekli.

    `timestamp` KRONOLOJİK sıralama için zorunlu — hayatta kalma sorusu
    tanımı gereği zaman sıralıdır; rastgele bölünmüş pencereler
    "keşiften sonra ne oldu" sorusunu cevaplayamaz.

    Her örüntü için:
      discovery      — örüntünün yeterli örneğe ulaştığı İLK pencere
                       (WR + o pencerenin tabanı + fazlalık)
      subsequent     — sonraki her pencere, aynı üçlü
      mean_subsequent_excess
      decay          — sonraki ortalama fazlalık − keşif fazlalığı.
                       NEGATİF = örüntü eriyor.
      consistent_chunks — fazlalığın pozitif kaldığı pencere sayısı
      verdict        — "surviving" / "decaying" / "collapsed" /
                       "insufficient_history"
      by_regime      — rejim başına {n, win_rate, baseline, excess}.
                       Taban O REJİMİN kendi oranı: "bearish_low'da
                       herkes kaybediyor" ile "bu örüntü bearish_low'da
                       kaybediyor" birbirinden ayrılıyor."""
    usable = [
        r for r in records
        if isinstance(r.get("patterns"), list)
        and isinstance(r.get("won"), bool)
        and r.get("timestamp") is not None
    ]
    if len(usable) < chunk_size * 2:
        return None

    ordered = sorted(usable, key=lambda r: r["timestamp"])
    chunks = [ordered[i:i + chunk_size] for i in range(0, len(ordered), chunk_size)]
    # Son pencere yarım kalmışsa atılıyor -- kısa bir pencerenin WR'ı
    # diğerleriyle kıyaslanabilir değil.
    chunks = [c for c in chunks if len(c) >= chunk_size]
    if len(chunks) < 2:
        return None

    pattern_names: set[str] = set()
    for r in ordered:
        pattern_names.update(r["patterns"])

    patterns: dict[str, dict] = {}
    for name in sorted(pattern_names):
        windows = []
        for index, chunk in enumerate(chunks):
            members = [r for r in chunk if name in r["patterns"]]
            others = [r for r in chunk if name not in r["patterns"]]
            if len(members) < min_per_chunk or not others:
                continue
            windows.append({
                "chunk": index,
                "n": len(members),
                "win_rate": round(_win_rate(members), 6),
                # Taban AYNI pencerenin GERİ KALANI -- piyasa kayması
                # fazlalıktan düşüyor, örüntünün kendi payı tabanı
                # kirletmiyor (bkz. modül notu).
                "baseline": round(_win_rate(others), 6),
                "excess": round(_win_rate(members) - _win_rate(others), 6),
            })

        if len(windows) < 2:
            patterns[name] = {
                "windows": windows, "usable": False,
                "verdict": "insufficient_history", "decay": None,
            }
            continue

        discovery = windows[0]
        subsequent = windows[1:]
        mean_subsequent = sum(w["excess"] for w in subsequent) / len(subsequent)
        positive = sum(1 for w in subsequent if w["excess"] > 0)

        if mean_subsequent <= 0:
            verdict = "collapsed"
        elif mean_subsequent >= discovery["excess"] - SURVIVAL_BAND:
            verdict = "surviving"
        else:
            verdict = "decaying"

        # Rejim kırılımı -- havuzlanmış sayı "hangi rejimde anlamlı"
        # sorusunu gizler.
        by_regime: dict[str, dict] = {}
        for regime in sorted({r.get("regime") for r in ordered if r.get("regime")}):
            regime_all = [r for r in ordered if r.get("regime") == regime]
            regime_members = [r for r in regime_all if name in r["patterns"]]
            regime_others = [r for r in regime_all if name not in r["patterns"]]
            if len(regime_members) < MIN_PER_REGIME or len(regime_others) < MIN_PER_REGIME:
                by_regime[regime] = {"n": len(regime_members), "usable": False, "excess": None}
                continue
            by_regime[regime] = {
                "n": len(regime_members),
                "win_rate": round(_win_rate(regime_members), 6),
                "baseline": round(_win_rate(regime_others), 6),
                "excess": round(_win_rate(regime_members) - _win_rate(regime_others), 6),
                "usable": True,
            }

        patterns[name] = {
            "discovery": discovery,
            "subsequent": subsequent,
            "mean_subsequent_excess": round(mean_subsequent, 6),
            "decay": round(mean_subsequent - discovery["excess"], 6),
            "consistent_chunks": positive,
            "total_subsequent_chunks": len(subsequent),
            "by_regime": by_regime,
            "best_regime": (
                max(
                    (k for k, v in by_regime.items() if v["usable"]),
                    key=lambda k: by_regime[k]["excess"], default=None,
                )
            ),
            "worst_regime": (
                min(
                    (k for k, v in by_regime.items() if v["usable"]),
                    key=lambda k: by_regime[k]["excess"], default=None,
                )
            ),
            "usable": True,
            "verdict": verdict,
        }

    surviving = sorted(
        (k for k, v in patterns.items() if v.get("verdict") == "surviving"),
        key=lambda k: -patterns[k]["mean_subsequent_excess"],
    )
    return {
        "sample_size": len(ordered),
        "chunks": len(chunks),
        "chunk_size": chunk_size,
        "patterns": patterns,
        "surviving_patterns": surviving,
        "collapsed_patterns": sorted(
            k for k, v in patterns.items() if v.get("verdict") == "collapsed"
        ),
        "survival_band": SURVIVAL_BAND,
    }
