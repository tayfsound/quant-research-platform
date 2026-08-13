"""Adversarial Intelligence — Faz 941-970 (Cognitive Core 7.0).

backtest/red_team.py SENTETİK senaryolar (whipsaw, flash-crash, korele
çoklu-varlık çöküşü) üretip sistemi test ediyor — bu GERÇEK senaryolar
ama İCAT EDİLMİŞ fiyat yolları. Bu modül farklı bir yaklaşım: sistemin
GERÇEK geçmiş performansını koşul kovalarına göre tarayıp, EN KÖTÜ
performans gösterdiği GERÇEK koşulları (icat edilmiş bir senaryo değil,
GERÇEKTEN yaşanmış ve kayıtlı bir zayıflık) sistematik olarak buluyor —
"adversarial search," ama rastgele saldırı senaryosu üretmek yerine
sistemin KENDİ gerçek geçmişindeki en kötü noktalarını arıyor. Bu
bulgular red-team.py'ye YENİ, gerçek-veri-kaynaklı senaryo fikirleri
sağlayabilir.

Kasıtlı olarak SADECE tespit/rapor — hiçbir pozisyon/risk kararını burada
otomatik değiştirmiyor."""
from collections import defaultdict

MIN_GROUP_SIZE = 20
DEFAULT_TOP_N = 5


def find_worst_performing_conditions(
    trades: list[dict],
    group_by: tuple[str, ...] = ("direction", "regime", "volatility_regime"),
    min_group_size: int = MIN_GROUP_SIZE,
    top_n: int = DEFAULT_TOP_N,
) -> list[dict]:
    """trades: 'win' (bool) ve 'pnl' (float) alanları olan GERÇEK kapanmış
    işlemler. Kovalara göre gruplayıp win_rate'e (en düşükten en yükseğe)
    göre sıralı EN KÖTÜ top_n kovayı döner — bunlar sistemin gerçek,
    kayıtlı zayıf noktaları, hedefli inceleme/red-team senaryosu üretimi
    için. min_group_size altındaki kovalar fail-closed dışlanır (küçük
    örneklemden bir 'zayıflık' icat edilmez)."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for t in trades:
        if t.get("win") is None or t.get("pnl") is None:
            continue
        key_parts = [str(t.get(field, "unknown")) for field in group_by]
        groups[tuple(key_parts)].append(t)

    results = []
    for key, group_trades in groups.items():
        if len(group_trades) < min_group_size:
            continue
        wins = sum(1 for t in group_trades if t["win"])
        total_pnl = sum(t["pnl"] for t in group_trades)
        label = "|".join(f"{field}={value}" for field, value in zip(group_by, key))
        results.append({
            "condition": label,
            "sample_size": len(group_trades),
            "win_rate": round(wins / len(group_trades), 4),
            "total_pnl": round(total_pnl, 6),
            "avg_pnl": round(total_pnl / len(group_trades), 6),
        })

    results.sort(key=lambda r: r["win_rate"])
    return results[:top_n]
