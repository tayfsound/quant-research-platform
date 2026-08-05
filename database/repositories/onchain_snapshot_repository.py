"""Faz 196: on-chain metrik zaman serisi — sadece 24 saatlik delta
hesaplamak (örn. stablecoin_mint_24h) için gereken minimum tarihçe."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import text


class OnChainSnapshotRepository:
    def __init__(self, session):
        self.session = session

    def save(self, metric: str, value: float, time: datetime | None = None) -> None:
        self.session.execute(
            text("INSERT INTO onchain_snapshots (metric, time, value) VALUES (:metric, :time, :value)"),
            {"metric": metric, "time": time or datetime.now(UTC), "value": value},
        )
        self.session.commit()

    def get_delta_24h(self, metric: str, current_value: float) -> float | None:
        """~24 saat önceye en yakın kaydı bulup şimdiki değerden çıkarır.
        Öyle bir kayıt yoksa (ilk kurulum, henüz 24 saat geçmemiş) None
        döner — sıfır ya da icat edilmiş bir sayı değil, dürüstçe 'henüz
        bilmiyoruz'."""
        cutoff = datetime.now(UTC) - timedelta(hours=23)
        row = self.session.execute(
            text(
                "SELECT value FROM onchain_snapshots "
                "WHERE metric = :metric AND time <= :cutoff "
                "ORDER BY time DESC LIMIT 1"
            ),
            {"metric": metric, "cutoff": cutoff},
        ).first()

        if row is None:
            return None
        return current_value - row[0]
