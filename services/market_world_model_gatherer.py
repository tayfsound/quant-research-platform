"""Market World Model'ın girdisini GERÇEK kapanmış işlemlerden toplayan
tek kaynak — Cognitive Core 5.0-6.0 (Faz 901-940).
analytics/market_world_model.py::compute_block_bootstrap_paths() saf
(pure) kalıyor — gerçek veriye dokunan kod burada.

services/self_model_gatherer.py ile AYNI gerçek-getiri kaynağı (kronolojik
kapanmış işlemler, pump_fade_v1 hariç — mekanik strateji, council'in
gerçek getiri dağılımıyla ilgisi yok) — veri çekme icat/tekrar edilmiyor."""
from analytics.market_world_model import compute_block_bootstrap_paths
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

DEFAULT_BLOCK_SIZE = 10
DEFAULT_PATH_LENGTH = 50


def gather_market_world_model(
    block_size: int = DEFAULT_BLOCK_SIZE, path_length: int = DEFAULT_PATH_LENGTH,
) -> dict:
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(
            limit=2000, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )

    # Kronolojik sıraya çevir — list_closed_trades opened_at DESC döner,
    # Moving Block Bootstrap'in gerçek ardışık bağımlılık yapısını
    # koruyabilmesi için ESKİDEN YENİYE sıralanması gerekiyor.
    ordered = sorted(closed_trades, key=lambda t: t.get("closed_at") or t.get("opened_at"))

    returns = []
    for t in ordered:
        entry = t.get("entry_price")
        exit_price = t.get("exit_price")
        direction = t.get("direction")
        if entry and exit_price and direction:
            sign = 1.0 if direction == "LONG" else -1.0
            returns.append(sign * (exit_price - entry) / entry)

    paths = compute_block_bootstrap_paths(returns, block_size=block_size, path_length=path_length)
    return {
        "block_size": block_size,
        "path_length": path_length,
        "n_returns": len(returns),
        "paths": paths,
    }
