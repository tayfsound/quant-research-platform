"""Faz 319 — tek seferlik veri taşıma: agent_memory_history/agent_memory.json
-> agent_performance_records (Postgres/TimescaleDB, namespace='').

faz319 migration SADECE şemayı kurar (boş tablo) — gerçek geçmiş veri
(54.396 kayıt, 10 domain, doğrulandı 2026-08-20) bilinçli olarak burada,
ayrı bir adımda taşınıyor (decisions tablosundaki geçmiş veri
düzeltmeleriyle AYNI ilke, bkz. faz279/280/281/317 migration'ları).

Idempotent: id+timestamp birincil anahtarına ON CONFLICT DO NOTHING —
script iki kez çalıştırılsa da kayıt çoğalmaz. Tek argümansız çalıştırma:
    python scripts/migrate_agent_memory_to_postgres.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from contracts.agent_performance import AgentPerformanceRecord  # noqa: E402
from database.session_factory import SessionFactory  # noqa: E402
from services.agent_memory import _RECORD_COLUMNS  # noqa: E402

_JSON_PATH = Path(__file__).resolve().parent.parent / "agent_memory_history" / "agent_memory.json"


def main() -> None:
    if not _JSON_PATH.exists():
        print(f"Kaynak dosya yok: {_JSON_PATH} -- taşınacak bir şey yok.")
        return

    raw = json.loads(_JSON_PATH.read_text())
    total_seen = 0
    total_inserted = 0

    columns = ["namespace", *_RECORD_COLUMNS]
    placeholders = ", ".join(f":{c}" for c in columns)
    insert_sql = text(
        f"INSERT INTO agent_performance_records ({', '.join(columns)}) "
        f"VALUES ({placeholders}) ON CONFLICT (id, timestamp) DO NOTHING"
    )

    for domain, records in raw.items():
        with SessionFactory.get_session() as session:
            for r in records:
                total_seen += 1
                record = AgentPerformanceRecord.model_validate(r)
                payload = record.model_dump(mode="python")
                payload["namespace"] = ""
                result = session.execute(insert_sql, payload)
                total_inserted += result.rowcount
        print(f"{domain}: {len(records)} kayıt işlendi")

    print(f"\nToplam görülen: {total_seen}, yeni eklenen: {total_inserted} "
          f"(fark = zaten taşınmış/çakışan kayıt sayısı)")


if __name__ == "__main__":
    main()
