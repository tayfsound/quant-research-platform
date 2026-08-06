"""Faz 233: experiment_registry tablosu tamamen kaldırıldı.

Kullanıcı bulgusu: "Experiments de 20 deney görünüyor... Experimentsi
kaldıralım, depolama sıkıntısı da çektirebilir bize." Gerçek bulgu:
engines/cognitive_pipeline.py::RecordingStage HER gerçek karar için (WAIT
dahil, işlem açılsın açılmasın, watchlist'teki her sembol için) bu tabloya
1 satır yazıyordu — 4885 satır birikmişti, hiçbir ajan/karar mekanizması
bunu OKUMUYORDU (tamamen yazma-amaçlı bir git-sha denetim kaydıydı,
zaten try/except içinde sarılıydı). Kaldırılması bilişsel döngüyü hiç
etkilemiyor — sadece gereksiz DB büyümesini durduruyor.

contracts/experiment_registry.py::ExperimentRegistry.get_git_sha() hâlâ
duruyor (backtest_orchestrator.py'nin BacktestRun.git_sha alanı için
kullanılıyor, tabloyla ilgisi yok) — sadece tablo/repository/API/dashboard
kaldırıldı.

Revision ID: faz233
Revises: faz214
Create Date: 2026-08-07
"""
from alembic import op

revision = "faz233"
down_revision = "faz214"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("experiment_registry")


def downgrade() -> None:
    raise NotImplementedError(
        "experiment_registry kasıtlı olarak kaldırıldı (Faz 233) — geri "
        "almak isteniyorsa faz166'nın create_table'ını elle çalıştırın."
    )
