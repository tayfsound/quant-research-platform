"""Faz 239-241 — Online Meta-Learning scheduler.

services/weight_optimizer.py'nin insan-onay-kapısı deseninin birebir
aynısı, ama ağırlıklar yerine TechnicalAgent'ın kendi iç skorlama
katsayıları (θ) için. Yeni θ ASLA doğrudan canlıya uygulanmıyor — önce
walk-forward out-of-sample Sharpe'ı raporun kendi başarı kriterini
(>= +0.4) geçmeli, SONRA bir insan agent_tuning_approvals üzerinden
onaylamalı (bkz. AgentTuningApprovalRepository). İkisi de sağlanmadan
agents/registry.py hep mevcut sabit varsayılan katsayılara düşer
(fail-closed)."""
import json
from datetime import UTC, datetime, timedelta

import structlog

from agents.technical_agent import TechnicalAgentCoefficients
from contracts.agent_tuning_approval import AgentTuningApproval
from database.repositories.agent_tuning_approval_repository import AgentTuningApprovalRepository
from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from meta_optimizer.agent_tuner import (
    MIN_RECORDS_TO_OPTIMIZE,
    load_historical_technical_records,
    optimize_technical_agent_coefficients,
    walk_forward_validate,
)

logger = structlog.get_logger()

TECHNICAL_AGENT_ID = "technical_agent_v1"

# Faz 239 raporunun kendi başarı kriteri: out-of-sample Sharpe farkı
# (tuned - baseline) >= +0.4 olmadan bir θ insan onayına dahi sunulmuyor.
MIN_SHARPE_IMPROVEMENT = 0.4

_LAST_ATTEMPT_SETTINGS_KEY = "meta_learning_last_attempt"


def _record_last_attempt(reason: str, sample_count: int, sharpe_improvement: float | None) -> None:
    """Faz 363 — kullanıcı bulgusu: onaylı tur hiç yoksa dashboard
    ("Meta-Learning Effectiveness") sessizce boş görünüyordu, kullanıcı
    "neden hiç veri yok" diye tekrar tekrar soruyordu. propose_technical_
    agent_tuning fail-closed olduğu için (haftalık walk-forward eşiği
    geçilmezse hiçbir şey yazılmıyordu) sebep hiçbir yerde görünmüyordu.
    Başarılı/başarısız HER denemenin son sonucunu app_settings'e yazıyoruz
    (approvals tablosuna değil — o SADECE insana sunulan gerçek önerileri
    temsil ediyor, semantiğini bozmayalım) ki panel "neden boş" sorusunu
    dürüstçe cevaplayabilsin."""
    try:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set(
                _LAST_ATTEMPT_SETTINGS_KEY,
                json.dumps({
                    "timestamp": datetime.now(UTC).isoformat(),
                    "reason": reason,
                    "sample_count": sample_count,
                    "sharpe_improvement": sharpe_improvement,
                    "required_sharpe_improvement": MIN_SHARPE_IMPROVEMENT,
                }),
                updated_by="meta_learning_scheduler",
            )
    except Exception as exc:
        logger.warning("meta_learning_last_attempt_record_failed", error=str(exc))


def propose_technical_agent_tuning(agent_id: str = TECHNICAL_AGENT_ID) -> AgentTuningApproval | None:
    """Fail-closed: yetersiz veri, walk-forward'ın geçmemesi, ya da zaten
    bekleyen bir onay varsa None döner — hiçbir şey değişmez, icat edilmiş
    bir öneri asla oluşturulmaz."""
    records = load_historical_technical_records()
    if len(records) < MIN_RECORDS_TO_OPTIMIZE:
        logger.info(
            "meta_learning_skip_insufficient_data",
            agent_id=agent_id, sample_count=len(records), required=MIN_RECORDS_TO_OPTIMIZE,
        )
        _record_last_attempt("insufficient_data", len(records), None)
        return None

    with SessionFactory.get_session() as session:
        repo = AgentTuningApprovalRepository(session)
        if repo.has_pending(agent_id):
            return None

        wf_result = walk_forward_validate(records)
        improvement = wf_result.get("sharpe_improvement")
        if improvement is None or improvement < MIN_SHARPE_IMPROVEMENT:
            logger.info(
                "meta_learning_skip_walk_forward_not_passed",
                agent_id=agent_id, sharpe_improvement=improvement,
            )
            _record_last_attempt("walk_forward_not_passed", len(records), improvement)
            return None

        # Walk-forward sadece θ'nın GENELLEYİP genellemediğini kanıtlıyor
        # (kabul kapısı) — insan onayına sunulacak GERÇEK θ, elimizdeki
        # TÜM veriyle ayrı, son bir optimizasyonla bulunuyor (herhangi bir
        # tek fold'un θ'sı değil — mevcut en iyi bilgiyi kullanmak için).
        final_coeffs, in_sample_sharpe = optimize_technical_agent_coefficients(records)

        previous_row = repo.get_latest_approved(agent_id)
        previous_coefficients = (
            dict(previous_row.proposed_coefficients)
            if previous_row is not None
            else dict(TechnicalAgentCoefficients().__dict__)
        )

        approval = AgentTuningApproval(
            agent_id=agent_id,
            proposed_coefficients=dict(final_coeffs.__dict__),
            previous_coefficients=previous_coefficients,
            in_sample_sharpe=in_sample_sharpe,
            mean_oos_sharpe_tuned=wf_result["mean_oos_sharpe_tuned"],
            mean_oos_sharpe_baseline=wf_result["mean_oos_sharpe_baseline"],
            sharpe_improvement=improvement,
            sample_count=len(records),
            expires_at=datetime.now() + timedelta(days=7),
            status="pending",
        )
        repo.save(approval)
        logger.info(
            "meta_learning_tuning_proposed",
            agent_id=agent_id, sharpe_improvement=improvement, sample_count=len(records),
        )
        _record_last_attempt("proposed", len(records), improvement)
        return approval


def get_approved_technical_agent_coefficients(
    agent_id: str = TECHNICAL_AGENT_ID,
) -> TechnicalAgentCoefficients | None:
    """agents/registry.py::create_default() burayı çağırır. Onaylanmış bir
    θ yoksa (ya da DB'ye erişilemezse) None döner — çağıran taraf
    TechnicalAgentCoefficients() (mevcut sabit) varsayılanına düşer."""
    try:
        with SessionFactory.get_session() as session:
            repo = AgentTuningApprovalRepository(session)
            row = repo.get_latest_approved(agent_id)
            if row is None:
                return None
            return TechnicalAgentCoefficients(**row.proposed_coefficients)
    except Exception as exc:
        logger.warning("meta_learning_approved_coefficients_lookup_failed", error=str(exc))
        return None
