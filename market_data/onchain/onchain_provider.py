"""Faz 196/215: on-chain metrik motoru — SADECE gerçekten kolay ve dürüst
ölçülebilen metrikler. Proje sahibinin kendi sözleriyle: "zor olanları
icat etmeyelim... en önemli şey metriklerin doğru çalışması."

Bilinçli olarak YAPILMADI (indexer/etiketli adres listesi gerektirir,
Infura/Alchemy/Helius'un ücretsiz RPC erişimiyle dürüstçe hesaplanamaz):
exchange_inflow/outflow, whale accumulation/distribution, MVRV Z-Score.
Bunlar contracts/onchain.py'de hâlâ varsayılan (0.0/False) — icat edilmedi.

Gerçekten hesaplanan metrikler, hepsi tek bir çağrıyla:
- ETH gas price (Infura eth_gasPrice) — ağ talebinin doğrudan ölçüsü.
- USDT toplam arzı (Infura eth_call, ERC20 totalSupply()) — 24 saatlik
  deltası stablecoin_mint_24h'i besliyor.
- Solana TPS (Helius getRecentPerformanceSamples) — ağ aktivitesi.
- Faz 215: blockchain.info'nun tamamen ücretsiz/kimliksiz charts API'si —
  aktif adres sayısı trendi ve hash rate trendi (Bitcoin'e özel, gerçek
  ağ sağlığı göstergeleri — "whale accumulation" gibi yorumlanmış bir
  şey değil, dümdüz gözlemlenen sayılar)."""
import logging

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

_BLOCKCHAIN_INFO_CHARTS_URL = "https://api.blockchain.info/charts/{chart}"


def _fetch_blockchain_info_trend(chart: str, timespan: str = "14days") -> str | None:
    """Son değeri, aynı serinin önceki (bugün hariç) ortalamasıyla
    karşılaştırıp rising/falling/stable döndürür — FRED sağlayıcısının
    (market_data/macro/fred_provider.py) kullandığı yüzde-değişim
    yöntemiyle aynı, tutarlı yaklaşım."""
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
