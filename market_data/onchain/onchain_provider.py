"""Faz 196/215/268v: on-chain metrik motoru — SADECE gerçekten kolay ve
dürüst ölçülebilen metrikler. Proje sahibinin kendi sözleriyle: "zor
olanları icat etmeyelim... en önemli şey metriklerin doğru çalışması."

Faz 367-devam — kullanıcı isteği (2026-08-27, "onchain 13 gündür neden
sessiz" araştırmasının devamı): exchange_inflow/outflow artık GERÇEK
veriyle besleniyor — DefiLlama'nın ücretsiz, kimliksiz /protocol/{slug}
API'si, büyük borsaların KENDİ AÇIKLADIKLARI/etiketlenmiş cüzdanlarının
GERÇEK zincir-üstü toplam bakiyesini (TVL metodolojisi, "CEX Transparency")
günlük seri olarak veriyor — icat edilmiş bir tahmin değil, gerçek,
doğrulanabilir bir zincir-üstü ölçüm. Günlük bakiye DELTA'sı = net akış
(artış = net giriş/bearish, azalış = net çıkış/bullish) — tam da
agents/onchain_agent.py'nin zaten beklediği anlam. Aşağıda fetch_exchange_
net_flow_24h_usd() — bkz. kendi docstring'i.

whale_accumulation/whale_distribution HÂLÂ bilinçli olarak YAPILMADI —
DefiLlama'nın verisi BORSA cüzdanları için (etiketli, kamuya açık), ama
bireysel "balina" cüzdanlarını (borsa dışı büyük tutucular) etiketlemek
GERÇEK bir indexer/etiketli-adres veritabanı gerektirir (Nansen/Glassnode/
Whale Alert'in ücretli katmanları, ya da Whale Alert'in ücretsiz katmanı
— ayrı bir API key + hesap gerektiriyor, bu oturumda kullanıcıyla
konuşulmadı). contracts/onchain.py'de hâlâ varsayılan (False) — dürüstçe
icat edilmedi.

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
# Faz 309 — kullanıcı isteği: MVRV Z-SKORU (yukarıda, Faz 268v) DIŞINDA,
# düz MVRV ORANI (Z-skoru olmayan, ham piyasa-değeri/gerçekleşen-değer
# oranı) da isteniyordu. bitcoin-data.com'un AYNI ücretsiz Bitcoin Data
# API'sinde gerçekten var — 2026-08-20'de canlı doğrulandı:
# GET /v1/mvrv/last -> {"d":"2026-08-19","unixTs":...,"mvrv":1.3248}.
# NUPL/SOPR/Realized Price için de aynı ailede endpoint olduğu (bkz.
# https://api.bgeometrics.com/scalar.html) araştırmayla doğrulandı ama
# tam yolları saatlik kota (10/saat) doluyken teyit edilemedi — bilinen
# "/v1/{metrik}/last" kalıbına güvenerek kör tahmin eklemek yerine,
# SADECE gerçekten canlı test edilmiş MVRV eklendi.
_BITCOIN_DATA_MVRV_URL = "https://bitcoin-data.com/v1/mvrv/last"
# Faz 316-sonrası — kullanıcı isteği: yukarıdaki not "tam yolları saatlik
# kota doluyken teyit edilemedi" diyordu — kota tekrar açılınca (2026-08-20)
# üçü de CANLI doğrulandı: GET /v1/nupl/last -> {"nupl":0.2452},
# GET /v1/sopr/last -> {"sopr":1.0012},
# GET /v1/realized-price/last -> {"realizedPrice":52255.99}.
_BITCOIN_DATA_NUPL_URL = "https://bitcoin-data.com/v1/nupl/last"
_BITCOIN_DATA_SOPR_URL = "https://bitcoin-data.com/v1/sopr/last"
_BITCOIN_DATA_REALIZED_PRICE_URL = "https://bitcoin-data.com/v1/realized-price/last"
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
#
# Faz 367-devam — kritik bulgu (2026-08-27, kullanıcı sorusu: "onchain 13
# gündür neden sessiz"): eski _MVRV_CACHE saf bir Python dict'ti — HER
# ayrı süreç (uvicorn, celery worker, celery beat) kendi belleğinde AYRI
# bir kopyasını tutuyordu. 5 metrik (mvrv_zscore/mvrv_ratio/nupl/sopr/
# realized_price) × birden çok süreç, "her biri saatte 1 kez tazeliyor"
# sanılırken gerçekte saatte 8'lik PAYLAŞILAN limiti çok aşıyordu (canlı
# doğrulandı: 429 Too Many Requests). Redis'e taşındı — kim sorarsa
# sorsun AYNI taze/bayat veriyi okuyor, gerçek ağ isteğini sadece süreçlerin
# İLKİ yapıyor (mevcut services/tasks.py::_CycleLock ile AYNI redis.from_
# url(get_settings().REDIS_URL) deseni). Başarısızlık da (None) önbelleğe
# alınıyor — art arda hatalı isteklerle limiti tüketmemek için, eskisiyle
# AYNI ilke.
#
# Faz 367-devam — ikinci, daha temel bulgu (Redis düzeltmesinden HEMEN
# sonra, kullanıcı: "her şey tıkır tıkır çalışmalı"): süreçler-arası
# paylaşım tek başına YETERSİZ — asıl darboğaz GÜNLÜK 15 istek limiti.
# Canlıda GERÇEKTEN çağrılan 3 metrik var (mvrv_zscore/nupl/sopr — ikisi
# de agents/onchain_agent.py'de skorlamaya giriyor, bkz. kendi kodu;
# mvrv_ratio/realized_price hiçbir yerden çağrılmıyor, canlı bütçeyi hiç
# etkilemiyor). 1 saatlik TTL ile 3 metrik × 24 saat = günde 72 gerçek
# istek — günlük 15 limitini SAAT 5'TE bile aşar, günün geri kalanı
# kilitli kalırdı (paylaşılan önbellek bunu ÖNLEMEZ, sadece "kaç ayrı
# sürecin" istek attığını düzeltir, "ne sıklıkta" istek atıldığını değil).
# TTL 6 saate çıkarıldı: 3 metrik × (24/6=4) tazeleme/gün = günde 12
# gerçek istek — 15 limitinin güvenle altında, ~3 isteklik marj (soğuk
# önbellek/yeniden başlatma sonrası ilk tazeleme için).
_MVRV_CACHE_TTL_SECONDS = 6 * 3600
_MVRV_REDIS_KEY_PREFIX = "onchain:bitcoin_data:"
_MVRV_REDIS_MISSING_SENTINEL = "__none__"


def _redis_client():
    import redis

    return redis.from_url(get_settings().REDIS_URL)


def _fetch_bitcoin_data_metric(cache_key: str, url: str, json_field: str) -> float | None:
    """5 bitcoin-data.com fonksiyonunun (mvrv_zscore/mvrv_ratio/nupl/sopr/
    realized_price) PAYLAŞTIĞI tek gerçek fetch+önbellek mantığı — kod
    tekrarını önlemek ve Redis anahtarlarının tutarlı kalmasını garanti
    etmek için. Redis'e erişilemezse (ör. servis geçici olarak kapalı)
    fail-closed: önbellek atlanır, doğrudan (önbelleksiz) bir deneme
    yapılır — sistemin geri kalanı bundan etkilenmesin diye asla
    çökmez."""
    redis_key = _MVRV_REDIS_KEY_PREFIX + cache_key
    try:
        client = _redis_client()
        cached = client.get(redis_key)
    except Exception as exc:
        logger.warning("onchain Redis cache okunamadı (%s): %s", cache_key, exc)
        client = None
        cached = None

    if cached is not None:
        raw = cached.decode() if isinstance(cached, bytes) else cached
        return None if raw == _MVRV_REDIS_MISSING_SENTINEL else float(raw)

    try:
        response = httpx.get(url, timeout=10)
        response.raise_for_status()
        value = float(response.json()[json_field])
        to_store = str(value)
    except Exception as exc:
        logger.warning("bitcoin-data.com %s fetch failed: %s", cache_key, exc)
        value = None
        to_store = _MVRV_REDIS_MISSING_SENTINEL

    if client is not None:
        try:
            client.set(redis_key, to_store, ex=_MVRV_CACHE_TTL_SECONDS)
        except Exception as exc:
            logger.warning("onchain Redis cache yazılamadı (%s): %s", cache_key, exc)

    return value


_BITCOIN_DATA_CACHE_KEYS = ("mvrv_zscore", "mvrv_ratio", "nupl", "sopr", "realized_price")


def clear_bitcoin_data_cache_for_tests() -> None:
    """Testlerin eski _MVRV_CACHE.clear() yerine kullandığı yardımcı —
    Redis'teki 5 bilinen anahtarı siler. Sadece testler için (canlıda
    çağrılmaz, TTL kendiliğinden dolar)."""
    try:
        client = _redis_client()
        client.delete(*(_MVRV_REDIS_KEY_PREFIX + k for k in _BITCOIN_DATA_CACHE_KEYS))
    except Exception as exc:
        logger.warning("onchain Redis test-cache temizlenemedi: %s", exc)


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
    return _fetch_bitcoin_data_metric("mvrv_zscore", _BITCOIN_DATA_MVRV_ZSCORE_URL, "mvrvZscore")


def fetch_mvrv_ratio() -> float | None:
    """Faz 309 — düz MVRV oranı (Z-skoru DEĞİL, ham piyasa-değeri/
    gerçekleşen-değer oranı): >1 piyasa değeri gerçekleşen değerin
    üstünde (ortalama katılımcı kârda), <1 altında (ortalama katılımcı
    zararda). MVRV Z-Score'un (fetch_mvrv_zscore) AYNI ücretsiz kaynağı,
    AYNI önbellek disiplini (_MVRV_CACHE, 1 saat TTL — bitcoin-data.com'un
    sıkı 10/saat limitini aşmamak için ZORUNLU)."""
    return _fetch_bitcoin_data_metric("mvrv_ratio", _BITCOIN_DATA_MVRV_URL, "mvrv")


def fetch_nupl() -> float | None:
    """Faz 316-sonrası — Net Unrealized Profit/Loss: piyasadaki toplam
    kâr/zarar durumunun (gerçekleşen değere göre) net oranı. >0.75
    "euphoria" (tarihsel tepe bölgeleri), <0 "capitulation" (tarihsel dip
    bölgeleri) — klasik on-chain rejim sınıflandırması. MVRV ile AYNI
    ücretsiz kaynak/önbellek disiplini (1 saat TTL, bitcoin-data.com'un
    sıkı saatlik limitini aşmamak için ZORUNLU). Henüz hiçbir ajana
    bağlanmadı — MVRV ratio/Mayer Multiple gibi (bkz. o alanların kendi
    yorumları) sadece gözlem/gelecekteki kalibrasyon için."""
    return _fetch_bitcoin_data_metric("nupl", _BITCOIN_DATA_NUPL_URL, "nupl")


def fetch_sopr() -> float | None:
    """Faz 316-sonrası — Spent Output Profit Ratio: o gün hareket eden
    coinlerin ortalama olarak kârla mı zararla mı satıldığı (>1 kâr, <1
    zarar, ~1 "SOPR reset" — genelde yerel destek/direnç). Henüz hiçbir
    ajana bağlanmadı, sadece gözlem."""
    return _fetch_bitcoin_data_metric("sopr", _BITCOIN_DATA_SOPR_URL, "sopr")


def fetch_realized_price() -> float | None:
    """Faz 316-sonrası — Realized Price: piyasadaki tüm coinlerin son
    hareket ettikleri fiyatın ortalaması (MVRV oranının paydası, ham
    dolar cinsinden). Güncel fiyatla karşılaştırmak MVRV oranıyla AYNI
    bilgiyi verir ama mutlak bir "ortalama maliyet tabanı" seviyesi
    olarak da tek başına anlamlı. Henüz hiçbir ajana bağlanmadı, sadece
    gözlem."""
    return _fetch_bitcoin_data_metric("realized_price", _BITCOIN_DATA_REALIZED_PRICE_URL, "realizedPrice")


# Faz 367-devam — DefiLlama'nın TVL büyüklüğüne göre en büyük, gerçekten
# etiketli/açıklanmış zincir-üstü cüzdanları olan borsalar (Coinbase
# DefiLlama'da CEX olarak listelenmiyor — kendi rezerv adreslerini bu
# formatta açıklamıyor, dürüstçe dışarıda bırakıldı). 4 borsanın toplam
# günlük bakiye deltası, tek bir borsadan daha temsili bir "piyasa geneli"
# akış sinyali veriyor.
_DEFILLAMA_PROTOCOL_URL = "https://api.llama.fi/protocol/{slug}"
_EXCHANGE_FLOW_SLUGS = ("binance-cex", "okx", "bitfinex", "bybit")
_EXCHANGE_FLOW_CACHE_TTL_SECONDS = 3600
_EXCHANGE_FLOW_REDIS_KEY = "onchain:exchange_deltas_24h"


def _fetch_exchange_deltas() -> list[tuple[str, float]] | None:
    """fetch_exchange_net_flow_24h_usd() (piyasa geneli toplam) VE
    fetch_whale_like_exchange_flow()'un (tek borsadaki aykırı/yoğun
    hareket) PAYLAŞTIĞI tek gerçek fetch+önbellek — aynı ham veriyi iki
    kez ağdan çekmemek için. Her borsa için (slug, delta_usd) döner; bir
    borsa başarısız olursa SESSİZCE atlanır (icat edilmiş bir sayı asla
    üretilmez), en az 1 borsa başarılı olmalı, hiçbiri olmazsa None."""
    try:
        client = _redis_client()
        cached = client.get(_EXCHANGE_FLOW_REDIS_KEY)
    except Exception as exc:
        logger.warning("onchain Redis cache okunamadı (exchange_deltas): %s", exc)
        client = None
        cached = None

    if cached is not None:
        raw = cached.decode() if isinstance(cached, bytes) else cached
        if raw == _MVRV_REDIS_MISSING_SENTINEL:
            return None
        import json as _json

        return [(slug, delta) for slug, delta in _json.loads(raw)]

    deltas: list[tuple[str, float]] = []
    for slug in _EXCHANGE_FLOW_SLUGS:
        try:
            response = httpx.get(_DEFILLAMA_PROTOCOL_URL.format(slug=slug), timeout=15)
            response.raise_for_status()
            tvl_series = response.json().get("tvl") or []
            if len(tvl_series) < 2:
                continue
            today = tvl_series[-1]["totalLiquidityUSD"]
            yesterday = tvl_series[-2]["totalLiquidityUSD"]
            deltas.append((slug, today - yesterday))
        except Exception as exc:
            logger.warning("DefiLlama %s exchange balance fetch failed: %s", slug, exc)
            continue

    if client is not None:
        import json as _json

        to_store = _json.dumps(deltas) if deltas else _MVRV_REDIS_MISSING_SENTINEL
        try:
            client.set(_EXCHANGE_FLOW_REDIS_KEY, to_store, ex=_EXCHANGE_FLOW_CACHE_TTL_SECONDS)
        except Exception as exc:
            logger.warning("onchain Redis cache yazılamadı (exchange_deltas): %s", exc)

    return deltas or None


def fetch_exchange_net_flow_24h_usd() -> float | None:
    """Faz 367-devam — kullanıcı isteği (2026-08-27): agents/onchain_
    agent.py'nin exchange_inflow_24h/exchange_outflow_24h'i baştan beri
    hiç gerçek veriyle beslenmiyordu (bkz. bu modülün üst docstring'i).
    DefiLlama'nın ücretsiz, kimliksiz /protocol/{slug} API'si büyük
    borsaların KENDİ açıkladıkları zincir-üstü cüzdanlarının GERÇEK
    toplam bakiyesini günlük seri olarak veriyor (TVL metodolojisi,
    "CEX Transparency" — icat edilmiş bir tahmin değil). Son 2 günün
    bakiye deltası = net akış: pozitif (bakiye arttı) = net GİRİŞ
    (bearish, satış baskısı riski), negatif = net ÇIKIŞ (bullish).
    _EXCHANGE_FLOW_SLUGS'taki 4 büyük borsanın TOPLAMI — "piyasa geneli"
    yön sinyali (tek bir borsadan daha temsili).

    Dönen değer İŞARETLİ (pozitif=net giriş, negatif=net çıkış) — agents/
    onchain_agent.py'nin exchange_inflow_24h/exchange_outflow_24h çift-
    alan karşılaştırmasına services/context_adapter.py'de dönüştürülür."""
    deltas = _fetch_exchange_deltas()
    if not deltas:
        return None
    return sum(delta for _, delta in deltas)


# Faz 367-devam — kullanıcı isteği (2026-08-27): "balina birikimi/dağıtımı
# hâlâ yok" — gerçek bireysel balina cüzdan takibi (Whale Alert/Nansen/
# Arkham) araştırıldı, HİÇBİRİNİN ücretsiz katmanı yok (bkz. konuşma —
# Whale Alert $15-30/ay, Nansen kullanım-başına, Arkham kredi-bazlı,
# CryptoQuant $99/ay'dan başlıyor). Kullanıcı kararı: GEÇİCİ çözüm olarak
# borsa akışı verisinden dolaylı bir yaklaşım. Bu GERÇEK bir balina
# cüzdan takibi DEĞİL — 4 borsanın günlük bakiye deltalarından biri,
# DİĞERLERİNE göre orantısız derecede büyükse ("tek borsada yoğunlaşmış,
# piyasa geneli değil") bunu "muhtemelen tek, büyük bir işlem" (balina
# benzeri) olarak yorumluyoruz. fetch_exchange_net_flow_24h_usd (TOPLAM
# yön) ile ÇİFT SAYIM riskini azaltmak için kasıtlı olarak FARKLI bir
# soru soruyor: "toplam ne kadar" değil "TEK bir borsada anormal
# yoğunlaşma var mı" — ikisi aynı ham veriden türese de farklı bir
# özelliği (yön vs. yoğunlaşma) ölçüyor.
_WHALE_LIKE_MIN_ABS_USD = 300_000_000
_WHALE_LIKE_MIN_DOMINANCE_SHARE = 0.70


def fetch_whale_like_exchange_flow() -> tuple[str, float] | None:
    """DÜRÜST UYARI: gerçek bir balina cüzdan takibi değil, borsa akışı
    verisinden türetilmiş bir YAKLAŞIM (bkz. yukarıdaki modül notu) —
    services/context_adapter.py ve agents/onchain_agent.py'nin ürettiği
    caveat/evidence metinlerinde bu açıkça belirtiliyor, kullanıcı asla
    "gerçek balina verisi" sanmasın diye.

    En büyük |delta|'lı borsayı bulur; sadece HEM mutlak büyüklük
    ($300M+) HEM DE toplam mutlak hareketin baskın payı (%70+) sağlanırsa
    "anormal yoğunlaşma" (whale-like) olarak döner — (slug, signed_delta).
    Aksi halde (dağınık, piyasa-geneli bir hareket — zaten exchange_flow
    sinyaliyle kapsanıyor) None döner, çift sayım önlenir."""
    deltas = _fetch_exchange_deltas()
    if not deltas:
        return None

    total_abs = sum(abs(delta) for _, delta in deltas)
    if total_abs == 0:
        return None

    dominant_slug, dominant_delta = max(deltas, key=lambda pair: abs(pair[1]))
    if abs(dominant_delta) < _WHALE_LIKE_MIN_ABS_USD:
        return None
    if abs(dominant_delta) / total_abs < _WHALE_LIKE_MIN_DOMINANCE_SHARE:
        return None

    return dominant_slug, dominant_delta


def clear_exchange_flow_cache_for_tests() -> None:
    """clear_bitcoin_data_cache_for_tests() ile AYNI amaç — sadece testler
    için, fetch_exchange_net_flow_24h_usd()'nin ayrı Redis anahtarını
    siler."""
    try:
        client = _redis_client()
        client.delete(_EXCHANGE_FLOW_REDIS_KEY)
    except Exception as exc:
        logger.warning("onchain Redis test-cache temizlenemedi (exchange_flow): %s", exc)


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
