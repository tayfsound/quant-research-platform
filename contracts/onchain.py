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
