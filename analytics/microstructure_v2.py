"""Order Flow ve Microstructure v2 — Faz 394-418 (Cognitive Core 2.0).

agents/order_flow_agent.py zaten order_book_snapshots'tan (best bid/ask,
imbalance, funding, open interest) türetilen GERÇEK sinyaller kullanıyor.
Bu modül FARKLI bir gerçek veri kaynağını (market_trades — GERÇEK, işlem
bazlı fiyat/miktar/yön) kullanan, standart bir mikroyapı ölçüsü ekliyor:
Kyle'ın Lambda'sı (Kyle, 1985) — fiyatın birim İŞARETLİ hacim başına ne
kadar hareket ettiği, yani GERÇEK piyasa etkisi/likidite derinliği.
Yüksek lambda = az likit (küçük işlemler bile fiyatı ciddi hareket
ettiriyor), düşük/sıfıra yakın lambda = likit.

Kasıtlı olarak SADECE ölçüm/rapor — order_flow_agent'ın gerçek
confidence'ını burada otomatik DEĞİŞTİRMİYOR."""
import numpy as np

MIN_TRADE_SAMPLE_SIZE = 20


def compute_kyle_lambda(trades: list[dict]) -> dict | None:
    """trades: kronolojik SIRALI (en eskiden en yeniye) GERÇEK işlemler,
    her biri price/quantity/side ('buy'/'sell') alanları olan dict —
    market_data_repository.get_recent_trades()'in formatı (o DESC
    döndürür, çağıran taraf ters çevirmeli). <MIN_TRADE_SAMPLE_SIZE
    işlemle ya da işaretli hacimde hiç varyans yoksa (regresyon eğimi
    tanımsız) fail-closed None döner — icat edilmiş bir lambda asla
    üretilmez."""
    if len(trades) < MIN_TRADE_SAMPLE_SIZE:
        return None

    prices = np.array([float(t["price"]) for t in trades])
    price_changes = np.diff(prices)

    signed_volumes = np.array([
        float(t["quantity"]) * (1.0 if str(t.get("side", "")).lower() == "buy" else -1.0)
        for t in trades
    ])[1:]  # ilk işlemin bir önceki fiyata göre değişimi yok, hizalanıyor

    if len(price_changes) < 2 or signed_volumes.std() == 0:
        return None

    # np.cov (ddof=1) ile np.var (ddof=0 varsayılan) doğrudan bölünürse
    # normalize sabitleri UYUŞMAZ (N vs N-1) — basit doğrusal regresyon
    # eğimini (OLS) doğrudan, tutarlı bir şekilde hesaplıyoruz.
    x_centered = signed_volumes - signed_volumes.mean()
    y_centered = price_changes - price_changes.mean()
    kyle_lambda = float(np.sum(x_centered * y_centered) / np.sum(x_centered ** 2))
    avg_price = float(prices.mean())
    kyle_lambda_pct = (kyle_lambda / avg_price) if avg_price > 0 else None

    return {
        "kyle_lambda": round(kyle_lambda, 10),
        "kyle_lambda_pct": round(kyle_lambda_pct, 10) if kyle_lambda_pct is not None else None,
        "sample_size": len(trades),
    }
