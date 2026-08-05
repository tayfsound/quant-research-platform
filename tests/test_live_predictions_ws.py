"""Gap #18: /stream/live used to broadcast random.choice/random.uniform
fake data — LivePredictions.tsx displayed it as if it were a real model
output. Also, the route is registered under prefix="/api/v1" in api/main.py
but the frontend was connecting to a bare `ws://.../stream/live` (no
`/api/v1`), which would 404 in a real browser — never actually verified
end to end. This proves the real, correctly-routed endpoint streams a real
CognitiveOrchestrator.run_cycle() result.

Deliberately does NOT patch transformers.AutoModel/AutoTokenizer.from_pretrained
like most other tests — CognitiveOrchestrator.run_cycle() sets real market
features, which triggers the real embedding-based memory-lookup path (see
tests/test_embedding_semantic_search.py), and that path breaks under the
standard mock (gap #16). Uses the real, already locally-cached
all-MiniLM-L6-v2 model instead — no network call, no crash."""


def test_stream_live_broadcasts_a_real_orchestrator_cycle():
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    with client.websocket_connect("/api/v1/stream/live") as ws:
        data = ws.receive_json()

    assert data["direction"] in (-1, 0, 1)
    assert 0.0 <= data["confidence"] <= 1.0
    assert "rsi" in data["features"]
    assert "macd" in data["features"]
    assert data["symbol"]
