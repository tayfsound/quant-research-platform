"""Relative Strength Domain Contract — Faz 242-243."""
from pydantic import BaseModel


class RelativeStrengthContext(BaseModel):
    """Bu sembolün son dönem getirisinin, watchlist'teki DİĞER sembollerin
    (basket) ortalama getirisine göre nerede durduğu — klasik "relative
    strength" fikri, ama tek sembolün kendi geçmişine karşı değil, o an
    izlenen HAVUZA karşı ölçülüyor."""
    symbol_return_pct: float = 0.0
    basket_mean_return_pct: float = 0.0
    # Karşılaştırmada kullanılan GERÇEK veri bulunan diğer sembol sayısı —
    # 0 olabilir (ör. kripto olmayan bir sembol, ya da watchlist henüz
    # yeterince ingest edilmemiş) ve bu dürüstçe WAIT'e yol açar (icat
    # edilmiş bir karşılaştırma değil).
    basket_size: int = 0
    relative_strength_pct: float = 0.0  # symbol_return_pct - basket_mean_return_pct
