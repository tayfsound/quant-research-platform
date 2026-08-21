"""OnChain Domain Contracts."""
from datetime import datetime

from pydantic import BaseModel, Field


class OnChainContext(BaseModel):
    """OnChainAgent için zincir üstü bağlam."""
    exchange_inflow_24h: float = 0.0      # Borsalara giriş (USD)
    exchange_outflow_24h: float = 0.0     # Borsalardan çıkış (USD)
    whale_accumulation: bool = False       # Balinalar birikim yapıyor mu?
    whale_distribution: bool = False       # Balinalar dağıtıyor mu?
    stablecoin_mint_24h: float = 0.0      # Yeni basılan stablecoin (USD)
    active_addresses_24h: int = 0         # Aktif adres sayısı
    dormant_coins_moved: bool = False      # Uyuyan coin'ler uyandı mı?
    mvrv_zscore: float = 0.0              # Market Value to Realized Value Z-Score
    timestamp: datetime = Field(default_factory=datetime.now)
    # Faz 196: gerçekten ölçülen, "kolay/dürüst" iki ek metrik — indexer
    # gerektirmeyen, tek RPC çağrısıyla alınan gerçek değerler.
    eth_gas_price_gwei: float | None = None
    solana_tps: float | None = None
    # Faz 215: blockchain.info'nun ücretsiz/kimliksiz charts API'sinden —
    # Bitcoin'e özel, gerçek ağ sağlığı trendleri (rising/falling/stable).
    #
    # Faz 224 review bulgusu (C): bu iki alan SADECE Bitcoin zincirinden
    # geliyor ama TÜM kripto sembolleri (ETHUSDT, SOLUSDT dahil) için
    # aynı değeri taşıyor — ETH/SOL işlemlerinde "zincire özel" bir sinyal
    # değil, "genel kripto piyasası sağlığı" göstergesi olarak kullanılıyor.
    # Bu KASITLI: eth_gas_price_gwei/solana_tps de aynı şekilde tüm
    # sembollere uygulanıyor (bkz. ContextAdapter._real_onchain_metrics).
    # ETH'e özgü bir eşdeğer (ör. Etherscan günlük işlem sayısı — ETH artık
    # PoS, "hash rate" kavramı yok) veya SOL'e özgü bir eşdeğer henüz
    # eklenmedi; eklenirse OnChainAgent'a sembol bazlı yeni kanıt satırları
    # gerekir. Şimdilik bilinçli bir kapsam sınırı, kod hatası değil.
    network_activity_trend: str = "stable"
    hash_rate_trend: str = "stable"
    # Faz 335 — kullanıcı bulgusu: NUPL/SOPR fetch fonksiyonları Faz
    # 316-sonrası'nda yazılıp test edilmişti ama hiçbir ajana hiç
    # bağlanmamıştı ("hazırlandı, kullanılmadı" — kullanıcının kendi
    # sözleriyle "istediğim metrikler entegre edilmemiş"). MVRV Z-Score
    # ile AYNI desen: ikisi de bitcoin-data.com'dan, TÜM kripto
    # sembollerine "genel piyasa koşulu" olarak uygulanan cyclical
    # valuation göstergeleri (chain-özel teknik sağlık metrikleri
    # değil — network_activity_trend/hash_rate_trend'in aksine is_btc
    # ile sınırlanmıyor).
    nupl: float | None = None
    sopr: float | None = None
    # Faz 248: kritik bulgu — network_activity_trend/hash_rate_trend SADECE
    # Bitcoin zincirinden geliyor (yukarıdaki not, Faz 224 review bulgusu C)
    # ama agents/onchain_agent.py bunları TÜM sembollere (ETHUSDT, SOLUSDT
    # dahil) aynen yön puanına uyguluyordu — ETH/SOL işlem alırken aslında
    # BTC'nin ağ sağlığına göre karar veriliyordu. symbol alanı, ajanın bu
    # BTC-özel sinyalleri SADECE gerçekten BTC işlem alırken yön puanına
    # katmasını, diğer sembollerde sadece bilgi notu (evidence) olarak
    # bırakmasını sağlıyor.
    symbol: str = ""
