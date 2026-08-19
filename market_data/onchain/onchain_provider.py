"""Faz 196/215/268v: on-chain metrik motoru — SADECE gerçekten kolay ve
dürüst ölçülebilen metrikler. Proje sahibinin kendi sözleriyle: "zor
olanları icat etmeyelim... en önemli şey metriklerin doğru çalışması."

Bilinçli olarak YAPILMADI (indexer/etiketli adres listesi gerektirir,
Infura/Alchemy/Helius'un ücretsiz RPC erişimiyle dürüstçe hesaplanamaz):
exchange_inflow/outflow, whale accumulation/distribution. Bunlar
contracts/onchain.py'de hâlâ varsayılan (0.0/False) — icat edilmedi.

Faz 308 — kullanıcı isteği: Glassnode tarzı ileri düzey bir metrik listesi
(MVRV bantları, STH/LTH davranış kohortları, cost basis dağılım heatmap'i,
HODL waves, "percent supply in profit", realized cap/liveliness) araştırıldı.
AYNI ilkeyle bilinçli olarak YAPILMADI: bunların hepsi UTXO-yaş kohort
analizi gerektirir — tam bir Bitcoin node + özel bir indexer (ya da
Glassnode/CryptoQuant'ın ücretli katmanı) olmadan dürüstçe hesaplanamaz,
ücretsiz/kimliksiz bir API'de gerçek karşılığı yok. MVRV Z-Score (Faz
268v, aşağıda) bu ailenin ücretsiz/dürüst şekilde erişilebilen TEK üyesi.

Gerçekten hesaplanan metrikler:
- ETH gas price (Infura eth_gasPrice) — ağ talebinin doğrudan ölçüsü.
- USDT toplam arzı (Infura eth_call, ERC20 totalSupply()) — 24 saatlik
  deltası stablecoin_mint_24h'i besliyor.
- Solana TPS (Helius getRecentPerformanceSamples) — ağ aktivitesi.
- Faz 215: blockchain.info'nun tamamen ücretsiz/kimliksiz charts API'si —
  aktif adres sayısı trendi ve hash rate trendi (Bitcoin'e özel, gerçek
  ağ sağlığı göstergeleri — "whale accumulation" gibi yorumlanmış bir
  şey değil, dümdüz gözlemlenen sayılar).
- Faz 268v: kullanıcı isteği — MVRV Z-Score, X/Twitter'dan (yapılandırılmamış,
  güvenilmez bir kaynak — bkz. konuşma) çekmek yerine gerçek, yapılandırılmış,
  ücretsiz bir API'den (bitcoin-data.com / BGeometrics Bitcoin Data API) —
  API key GEREKTİRMİYOR, gerçek güncel veri döndürüyor (doğrulandı:
  2026-08-10 için 0.4177). agents/onchain_agent.py'nin mvrv_zscore skorlama
  mantığı zaten vardı (Faz 196'dan beri), sadece hiç gerçek veriyle
  beslenmiyordu."""
import logging
import time

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

_BLOCKCHAIN_INFO_CHARTS_URL = "https://api.blockchain.info/charts/{chart}"
_BITCOIN_DATA_MVRV_ZSCORE_URL = "https://bitcoin-data.com/v1/mvrv-zscore/last"
# Faz 306 — kullanıcı isteği: pump-fade'in gerçek risk sürücüsünün BTC
# yönü değil "kaç coin aynı anda pompalanıyor" yoğunluğu olduğu (bkz.
# services/pump_fade_strategy.py::_compute_density_size_multiplier)
# tespit edildikten sonra, bunu BTC dominansı/"altseason" göstergesiyle
# birleştirme niyeti konuşuldu. CoinGecko'nun ücretsiz, API-key
# gerektirmeyen /global uç noktası TEK istekte hem BTC dominansını hem
# TOTAL2/TOTAL3'ü (TradingView'in yaygın kullandığı, BTC/BTC+ETH hariç
# toplam piyasa değeri endeksleri) türetmeye yetecek ham veriyi veriyor —
# ayrı bir endeks API'sine gerek yok.
_COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"

# Faz 268v: bitcoin-data.com'un ücretsiz katmanı 8 istek/saat, 15 istek/gün
# ile sınırlı — MVRV zaten günlük değişen bir metrik, agresif bir önbellek
# hem bu limiti aşmamak hem de gereksiz ağ trafiğini önlemek için ZORUNLU.
_MVRV_CACHE: dict[str, tuple[float, float | None]] = {}
_MVRV_CACHE_TTL_SECONDS = 3600

# Faz 268j — gerçek olay: bir walk-forward backtest'te (15 sembol, 5m,
# 1000 bar) HER TEK bar için bu modüldeki 5 fonksiyon (yalnızca MVRV hariç)
# önbelleksiz, taze bir ağ isteği atıyordu — canlı log'da bar başına ~2.2sn
# gecikme, ~900 bar/sembol × 15 sembol'de saatler sürecek bir backtest'e
# yol açtı (kullanıcı "yarım saat oldu bitmedi" diye fark etti). Üstelik
# bunlar HER ZAMAN "şu an"ki gerçek zamanlı veriyi çekiyordu — geçmiş bir
# bar'ı değerlendirirken bile bugünün gas price/hash rate/TPS'i kullanmak
# demek, aslında o an bilinmeyen bir bilginin geçmişe sızması (look-ahead
# bias). MVRV zaten bu kalıbı kullanıyordu (Faz 268v) — aynısı diğer 4
# fonksiyona da uygulandı. Bu, HIZ sorununu çözer (aynı process içindeki
# tekrarlanan barlar artık tek bir ağ isteğini paylaşır); look-ahead
# sorununu TAM olarak çözmez (hâlâ "şu an"ın verisi, gerçek o-tarihli
# geçmiş veri değil) — bu, ücretsiz/kimliksiz API'lerin gerçek bir
# yapısal sınırı, icat edilmiş bir çözüm eklenmedi.
_GENERIC_CACHE_TTL_SECONDS = 3600
_generic_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, fetch_fn):
    cached = _generic_cache.get(key)
    if cached and (time.monotonic() - cached[0]) < _GENERIC_CACHE_TTL_SECONDS:
        return cached[1]
    value = fetch_fn()
    _generic_cache[key] = (time.monotonic(), value)
    return value


def _fetch_blockchain_info_trend(chart: str, timespan: str = "14days") -> str | None:
    """Son değeri, aynı serinin önceki (bugün hariç) ortalamasıyla
    karşılaştırıp rising/falling/stable döndürür — FRED sağlayıcısının
    (market_data/macro/fred_provider.py) kullandığı yüzde-değişim
    yöntemiyle aynı, tutarlı yaklaşım."""
    def _do_fetch() -> str | None:
        try:
            response = httpx.get(
                _BLOCKCHAIN_INFO_CHARTS_URL.format(chart=chart),
                params={"timespan": timespan, "format": "json"},
                timeout=10,
            )
            response.raise_for_status()
            values = [v["y"] for v in response.json().get("values", [])]
            if len(values) < 5:
                return None

            current = values[-1]
            baseline = sum(values[:-1]) / len(values[:-1])
            if baseline == 0:
                return None
            pct_change = (current - baseline) / abs(baseline)

            if pct_change > 0.05:
                return "rising"
            if pct_change < -0.05:
                return "falling"
            return "stable"
        except Exception as exc:
            logger.warning("blockchain.info chart fetch failed (%s): %s", chart, exc)
            return None

    return _cached(f"blockchain_info_trend:{chart}:{timespan}", _do_fetch)


def fetch_network_activity_trend() -> str | None:
    """Aktif Bitcoin adresi sayısının son 14 günlük trendi — gerçek ağ
    kullanımı, "whale accumulation" gibi yorumlanmış bir tahmin değil."""
    return _fetch_blockchain_info_trend("n-unique-addresses")


def fetch_hash_rate_trend() -> str | None:
    """Bitcoin hash rate trendi — madencilerin uzun vadeli ağa
    yatırımının gerçek bir göstergesi (sürekli düşüş genelde madenci
    kapitülasyonuyla ilişkilendirilir)."""
    return _fetch_blockchain_info_trend("hash-rate")

# Etherscan/ethplorer'da doğrulanmış gerçek USDT (Tether) ERC20 kontrat
# adresi — WebSearch ile doğrulandı, elle yazılan bir adres kullanılmadı
# (Ethereum adresleri 40 hex karakterdir, tek bir karakter hatası bile
# tamamen farklı/geçersiz bir kontrata işaret edebilir).
USDT_CONTRACT_ADDRESS = "0xdac17f958d2ee523a2206206994597c13d831ec7"
_TOTAL_SUPPLY_SELECTOR = "0x18160ddd"


def _infura_rpc(method: str, params: list) -> dict | None:
    def _do_call() -> dict | None:
        settings = get_settings()
        url = settings.INFURA_MAINNET_URL
        if not url:
            return None
        try:
            response = httpx.post(
                url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                logger.warning("Infura RPC error (%s): %s", method, data["error"])
                return None
            return data
        except Exception as exc:
            logger.warning("Infura RPC call failed (%s): %s", method, exc)
            return None

    return _cached(f"infura_rpc:{method}:{params}", _do_call)


def fetch_eth_gas_price_gwei() -> float | None:
    data = _infura_rpc("eth_gasPrice", [])
    if not data:
        return None
    wei = int(data["result"], 16)
    return wei / 1e9


def fetch_usdt_total_supply() -> float | None:
    data = _infura_rpc("eth_call", [{"to": USDT_CONTRACT_ADDRESS, "data": _TOTAL_SUPPLY_SELECTOR}, "latest"])
    if not data:
        return None
    raw = int(data["result"], 16)
    return raw / 1e6  # USDT 6 ondalık basamak kullanır


def fetch_solana_tps() -> float | None:
    def _do_fetch() -> float | None:
        settings = get_settings()
        if not settings.HELIUS_API_KEY:
            return None
        url = f"https://mainnet.helius-rpc.com/?api-key={settings.HELIUS_API_KEY}"
        try:
            response = httpx.post(
                url,
                json={"jsonrpc": "2.0", "id": 1, "method": "getRecentPerformanceSamples", "params": [1]},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            samples = data.get("result") or []
            if not samples:
                return None
            sample = samples[0]
            period = sample.get("samplePeriodSecs") or 1
            return sample.get("numTransactions", 0) / period
        except Exception as exc:
            logger.warning("Helius RPC call failed: %s", exc)
            return None

    return _cached("solana_tps", _do_fetch)


def fetch_mvrv_zscore() -> float | None:
    """Faz 268v: BGeometrics'in ücretsiz, API key gerektirmeyen Bitcoin
    Data API'sinden gerçek, güncel MVRV Z-Score — piyasa değerinin
    gerçekleşen değere (realized value) göre kaç standart sapma uzakta
    olduğunu gösteren, gerçek on-chain veriden hesaplanmış bir aşırı-
    değerleme/ucuzluk göstergesi. agents/onchain_agent.py bunu zaten
    skorluyordu (>3.0 aşırı değerli -> SHORT, <-1.0 aşırı ucuz -> LONG),
    sadece hiç gerçek veriyle beslenmiyordu. Bitcoin'e özel bir metrik —
    diğer network sağlığı göstergeleri (network_activity_trend/
    hash_rate_trend) gibi tüm kripto sembollerine "genel piyasa koşulu"
    olarak uygulanıyor (bkz. services/context_adapter.py)."""
    cached = _MVRV_CACHE.get("mvrv_zscore")
    if cached and (time.monotonic() - cached[0]) < _MVRV_CACHE_TTL_SECONDS:
        return cached[1]

    try:
        response = httpx.get(_BITCOIN_DATA_MVRV_ZSCORE_URL, timeout=10)
        response.raise_for_status()
        value = float(response.json()["mvrvZscore"])
        _MVRV_CACHE["mvrv_zscore"] = (time.monotonic(), value)
        return value
    except Exception as exc:
        logger.warning("bitcoin-data.com MVRV Z-Score fetch failed: %s", exc)
        # Başarısızlığı da önbelleğe alıyoruz — art arda hatalı isteklerle
        # zaten sıkı olan 8/saat limitini tüketmeyelim.
        _MVRV_CACHE["mvrv_zscore"] = (time.monotonic(), None)
        return None


def _fetch_global_market_data() -> dict | None:
    def _do_fetch() -> dict | None:
        try:
            response = httpx.get(_COINGECKO_GLOBAL_URL, timeout=10)
            response.raise_for_status()
            return response.json()["data"]
        except Exception as exc:
            logger.warning("CoinGecko global market data fetch failed: %s", exc)
            return None

    return _cached("coingecko_global", _do_fetch)


def fetch_btc_dominance_pct() -> float | None:
    """BTC'nin toplam kripto piyasa değeri içindeki payı (%) — "altseason"
    (BTC dışı coinlerin BTC'ye göre güçlendiği dönem) tespitinin temel
    girdisi. Düşen dominans, sermayenin altcoin'lere aktığının klasik
    göstergesidir — pump-fade'in "kaç coin aynı anda pompalanıyor"
    yoğunluk sinyaliyle (services/pump_fade_strategy.py) BİRLİKTE
    yorumlanması gereken, ayrı ve bağımsız bir kanıt."""
    data = _fetch_global_market_data()
    if not data:
        return None
    return data.get("market_cap_percentage", {}).get("btc")


def fetch_total2_total3_market_cap_usd() -> dict | None:
    """TOTAL2 (BTC hariç toplam piyasa değeri) ve TOTAL3 (BTC+ETH hariç) —
    TradingView'in yaygın kullanılan endeksleriyle AYNI tanım, CoinGecko'nun
    ham total_market_cap + market_cap_percentage'ından türetilmiş."""
    data = _fetch_global_market_data()
    if not data:
        return None
    total = data.get("total_market_cap", {}).get("usd")
    pct = data.get("market_cap_percentage", {})
    btc_pct = pct.get("btc")
    eth_pct = pct.get("eth")
    if total is None or btc_pct is None or eth_pct is None:
        return None
    return {
        "total2_usd": total * (1 - btc_pct / 100),
        "total3_usd": total * (1 - (btc_pct + eth_pct) / 100),
    }


# Faz 308 — kullanıcı isteği: stabilcoin dominansı (USDT+USDC+... payı) vs
# ETH — "sermaye stabile mi kaçıyor yoksa altcoin'lere mi (ETH temsilci)
# akıyor" sorusunu, TEK bir kova yerine gerçek bileşenleriyle (CoinGecko
# market_cap_percentage'da zaten ayrı ayrı listeleniyor) ölçmek için.
# AYNI önbelleklenmiş /global çağrısını paylaşıyor — sıfır ek ağ maliyeti.
_STABLECOIN_SYMBOLS = ("usdt", "usdc", "usde", "dai", "fdusd", "usds", "usdt0")


def fetch_stablecoin_dominance_vs_eth_pct() -> dict | None:
    """market_cap_percentage'daki bilinen stabilcoin sembollerinin toplamı
    ile ETH'nin payını yan yana döner — hangisinin büyüdüğü, "risk-off'a
    (stabile) mi yoksa risk-on'a (altcoin, ETH temsilci) mi kaçış var"
    sorusuna kaba ama gerçek bir cevap verir. Bilinmeyen/yeni bir stabilcoin
    listede çıkarsa (icat edilmiş bir tahmin yerine) sessizce dışarıda
    kalır — toplam hafifçe eksik sayılabilir, asla fazla değil."""
    data = _fetch_global_market_data()
    if not data:
        return None
    pct = data.get("market_cap_percentage", {})
    eth_pct = pct.get("eth")
    if eth_pct is None:
        return None
    stablecoin_pct = sum(pct.get(sym, 0.0) for sym in _STABLECOIN_SYMBOLS)
    return {"stablecoin_dominance_pct": round(stablecoin_pct, 4), "eth_dominance_pct": eth_pct}


def fetch_mayer_multiple() -> float | None:
    """Mayer Multiple = güncel BTC fiyatı / 200 günlük basit hareketli
    ortalama. Klasik bir piyasa-döngüsü göstergesi (>2.4 tarihsel olarak
    aşırı ısınmış, <0.8 tarihsel olarak aşırı soğuk bölge) — ama GERÇEKTE
    bir on-chain metrik DEĞİL, sadece fiyattan türetilir. Burada
    gruplanmasının nedeni: kullanıcının istediği "BTC makro-döngü"
    göstergeleri (MVRV, dominans vb.) ile AYNI yorumlama bağlamında
    kullanılıyor olması — ama hiçbir yeni harici API'ye ihtiyaç duymuyor,
    zaten var olan OHLCV sağlayıcısından (market_data/ingestion) hesaplanır.
    <200 günlük gerçek veri varsa fail-closed None (icat edilmiş bir
    ortalama asla üretilmez)."""
    from market_data.ingestion.data_provider import get_ohlcv_provider

    def _do_compute() -> float | None:
        try:
            bars = get_ohlcv_provider().get_ohlcv("BTCUSDT", "1d", limit=200)
        except Exception as exc:
            logger.warning("Mayer Multiple fetch failed: %s", exc)
            return None
        if len(bars) < 200:
            return None
        closes = [b.close for b in bars]
        sma_200 = sum(closes) / len(closes)
        if sma_200 == 0:
            return None
        return closes[-1] / sma_200

    return _cached("mayer_multiple", _do_compute)
