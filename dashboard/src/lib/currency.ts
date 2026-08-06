// Faz 224: kullanıcı bulgusu — "PNL de para birimi görünmüyor bu hangi
// birimle kayıp belli değil dolar mı btc mi vs... Live predictions vs..
// her yerde aynı problem var." Sistemdeki tüm fiyat/PnL alanları zaten
// USD cinsinden hesaplanıyor (kripto çiftleri USDT'ye endeksli, USDT~USD;
// hisse/endeks zaten USD) — bu paylaşılan hook, kullanıcının Settings'ten
// seçtiği görüntüleme para birimine göre (USD/BTC/TRY) gerçek, canlı
// oranlarla (Binance BTCUSDT/USDTTRY) dönüştürüp formatlıyor. Hesaplama
// hep USD'de kalıyor — bu sadece görüntüleme katmanı.
import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";

export type DisplayCurrency = "USD" | "BTC" | "TRY";

type Rates = { usd_btc: number | null; usd_try: number | null };

const SYMBOLS: Record<DisplayCurrency, string> = { USD: "$", BTC: "₿", TRY: "₺" };

export function useCurrency() {
  const [currency, setCurrency] = useState<DisplayCurrency>("USD");
  const [rates, setRates] = useState<Rates>({ usd_btc: null, usd_try: null });

  useEffect(() => {
    fetch("/api/v1/settings/", { headers: authHeaders() })
      .then((r) => r.json())
      .then((d) => {
        const c = d.settings?.display_currency;
        if (c === "BTC" || c === "TRY" || c === "USD") setCurrency(c);
      })
      .catch(() => {});
    fetch("/api/v1/settings/currency-rates", { headers: authHeaders() })
      .then((r) => r.json())
      .then((d) => setRates({ usd_btc: d.usd_btc ?? null, usd_try: d.usd_try ?? null }))
      .catch(() => {});
  }, []);

  const format = (usdValue: number | null | undefined, digits = 2): string => {
    if (usdValue === null || usdValue === undefined || Number.isNaN(usdValue)) return "—";

    if (currency === "BTC" && rates.usd_btc) {
      return `${SYMBOLS.BTC}${(usdValue * rates.usd_btc).toLocaleString(undefined, {
        maximumFractionDigits: 8,
      })}`;
    }
    if (currency === "TRY" && rates.usd_try) {
      return `${SYMBOLS.TRY}${(usdValue * rates.usd_try).toLocaleString(undefined, {
        maximumFractionDigits: digits,
      })}`;
    }
    // USD, ya da seçilen para biriminin oranı henüz yüklenmediyse USD'ye düş.
    return `${SYMBOLS.USD}${usdValue.toLocaleString(undefined, { maximumFractionDigits: digits })}`;
  };

  return { currency, rates, format, symbol: SYMBOLS[currency] };
}
