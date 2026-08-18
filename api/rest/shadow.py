"""Shadow Mode: Macro-Only karşılaştırma — Faz 268-sonrası.

Kullanıcı bulgusu: 23 pozisyonluk örneklemde macro ajanının yönlü
tahminleri ~%86 isabetli görünüyordu. Kullanıcıyla üzerinde anlaşılan
çerçeve (3 seçenekten A): council'i sadeleştirmeden ÖNCE, macro-only bir
gölge stratejinin GERÇEK performansını (services/macro_shadow_tracker.py)
100+ kapanmış örneklem birikince council'in gerçek performansıyla
kıyaslamak. Bu endpoint her iki tarafı da AYNI ölçekte (fiyat getirisi
yüzdesi — leverage/pozisyon büyüklüğünden bağımsız, "yön doğru muydu"
sorusuna saf cevap) döndürür. Kasıtlı olarak SADECE ölçüm — hiçbir
otomatik "council'i küçült" eylemi tetiklemiyor."""
from fastapi import APIRouter, Depends

from database.repositories.decision_persistor import DecisionPersistor
from database.repositories.shadow_position_repository import ShadowPositionRepository
from database.session_factory import SessionFactory
from services.auth_service import AuthContext, get_current_user

router = APIRouter(prefix="/shadow", tags=["shadow"])


def _council_comparison_summary(session, min_sample_size: int) -> dict:
    """Council'in GERÇEK kapanmış işlemlerini shadow ile AYNI ölçekte
    (fiyat getirisi %) özetler — pump_fade_v1 hariç (o mekanik bir
    strateji, council'in yönlü karar kalitesiyle ilgisi yok)."""
    rows = DecisionPersistor(session).list_closed_trades(
        limit=100_000, exclude_experiment_bucket="pump_fade_v1"
    )
    pnl_series = []
    for r in sorted(rows, key=lambda r: r.get("closed_at") or r.get("opened_at")):
        entry = r.get("entry_price")
        exit_price = r.get("exit_price")
        direction = r.get("direction")
        if not entry or not exit_price or direction not in ("LONG", "SHORT"):
            continue
        sign = 1.0 if direction == "LONG" else -1.0
        pnl_series.append(sign * (exit_price - entry) / entry)

    total = len(pnl_series)
    if total == 0:
        return {
            "source": "council", "closed_count": 0, "win_rate": None,
            "avg_pnl_pct": None, "cumulative_pnl_pct": None,
            "max_drawdown_pct": None, "sample_size_sufficient": False,
        }

    wins = sum(1 for p in pnl_series if p > 0)
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for pnl in pnl_series:
        cumulative += pnl
        peak = max(peak, cumulative)
        max_drawdown = min(max_drawdown, cumulative - peak)

    return {
        "source": "council",
        "closed_count": total,
        "win_rate": round(wins / total, 3),
        "avg_pnl_pct": round(cumulative / total, 5),
        "cumulative_pnl_pct": round(cumulative, 5),
        "max_drawdown_pct": round(max_drawdown, 5),
        "sample_size_sufficient": total >= min_sample_size,
    }


@router.get("/comparison")
def shadow_comparison(min_sample_size: int = 100, user: AuthContext = Depends(get_current_user)):
    with SessionFactory.get_session() as session:
        macro_only = ShadowPositionRepository(session).comparison_summary(
            source="macro", min_sample_size=min_sample_size
        )
        council = _council_comparison_summary(session, min_sample_size)

    return {"macro_only": macro_only, "council": council}
