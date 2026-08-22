"""Replay Memory testleri."""
from ml.training.replay_memory import ReplayMemory


def test_replay_memory_circular_buffer():
    memory = ReplayMemory(capacity=3)

    for i in range(5):
        memory.add({
            "decision_id": f"id_{i}",
            "features": {"val": i},
            "label": i,
            "quality_score": 1.0,
            "timestamp": "2026-01-01"
        })

    assert len(memory) == 3
    # En son eklenenler: id_2, id_3, id_4 (circular olduğu için yerleşim değişebilir ama sayı sabittir)
    ids = [s.decision_id for s in memory.memory]
    assert "id_4" in ids
    assert "id_0" not in ids

def test_replay_memory_sampling():
    memory = ReplayMemory(capacity=10)

    # Düşük kaliteli örnek
    memory.add({
        "decision_id": "low",
        "features": {},
        "label": 0,
        "quality_score": 0.1,
        "timestamp": "2026-01-01"
    })

    # Yüksek kaliteli örnek
    memory.add({
        "decision_id": "high",
        "features": {},
        "label": 1,
        "quality_score": 0.9,
        "timestamp": "2026-01-01"
    })

    # Uniform sampling
    samples_uniform = memory.sample(batch_size=10, strategy="uniform")
    assert len(samples_uniform) == 2

    # Prioritized sampling (yüksek kaliteli olanın gelme olasılığı daha yüksek)
    # Çok sayıda örneklem alıp istatistiksel olarak kontrol edelim
    high_count = 0
    for _ in range(100):
        s = memory.sample(batch_size=1, strategy="prioritized")[0]
        if s.decision_id == "high":
            high_count += 1

    assert high_count > 70 # 0.9 / (0.9 + 0.1) = %90 olasılık, 70 emniyet payı
