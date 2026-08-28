"""Gap #16: EmbeddingService/SemanticSearch had never been exercised by any
test — the project's standard `patch("transformers.AutoModel/AutoTokenizer
.from_pretrained")` pattern (used everywhere else to keep the heavyweight
LLM reasoner path fast/offline in tests) breaks SentenceTransformer.encode():
sentence-transformers resolves `self.device` from the (now-mocked) model's
parameters, so `self.to(device)` gets handed a MagicMock and raises TypeError.

The fix isn't in the embedding code — EmbeddingService/SemanticSearch work
correctly against the real, already-locally-cached all-MiniLM-L6-v2 model,
no network call needed after the first download. The fix is knowing NOT to
apply the transformers auto-mock here (unlike every LLM-reasoner test), and
proving that with a real, unmocked, real-DB integration test."""
from unittest.mock import patch
from uuid import uuid4

from contracts.memory import Episode
from database.repositories.episode_repository import EpisodeRepository
from database.session_factory import SessionFactory
from services.embedding_service import EmbeddingService
from services.semantic_search import SemanticSearch


def test_embedding_service_produces_real_normalized_vectors():
    svc = EmbeddingService()
    vec = svc.encode_features({"RSI": 28.0, "ATR": 1.4}, symbol="BTCUSDT")

    assert len(vec) == 384
    norm = sum(v * v for v in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-4  # normalize_embeddings=True


def test_get_embedding_model_prefers_the_local_cache_with_no_network_call():
    """Faz 368 — kullanıcı bulgusu (gerçek olay): "RuntimeError: Cannot
    send a request, as the client has been closed", ~50dk'da 3 kez, her
    seferinde bir trading cycle'ın tamamı kayboluyordu. Kök neden: model
    zaten tam önbelleklenmiş olmasına rağmen her yüklemede yine de
    HuggingFace Hub'a gereksiz bir ağ isteği atılıyordu — bu ağ
    bağımlılığı, huggingface_hub'ın kendi HTTP istemcisindeki nadir bir
    yarış durumuyla birleşince çöküyordu. local_files_only=True artık
    ÖNCE deneniyor (önbellek varsa ağa HİÇ dokunmuyor) — bu testte
    gerçekten O YOLUN kullanıldığını (ağ-destekli yola hiç düşülmediğini)
    doğruluyoruz."""
    import services.embedding_service as embedding_service_module

    original_model = embedding_service_module._model
    embedding_service_module._model = None
    try:
        with patch("services.embedding_service.SentenceTransformer") as mock_ctor:
            mock_ctor.return_value = "fake-model"
            result = embedding_service_module.get_embedding_model()

        assert result == "fake-model"
        mock_ctor.assert_called_once_with("all-MiniLM-L6-v2", device="cpu", local_files_only=True)
    finally:
        embedding_service_module._model = original_model


def test_get_embedding_model_falls_back_when_local_cache_is_missing():
    """Önbellek yoksa (ör. taze bir deploy) fail-closed DEĞİL — normal
    (ağ destekli) yüklemeye düşülüyor, ilk kurulumda hâlâ çalışır."""
    import services.embedding_service as embedding_service_module

    original_model = embedding_service_module._model
    embedding_service_module._model = None
    try:
        with patch("services.embedding_service.SentenceTransformer") as mock_ctor:
            mock_ctor.side_effect = [OSError("not found in local cache"), "fake-model-from-network"]
            result = embedding_service_module.get_embedding_model()

        assert result == "fake-model-from-network"
        assert mock_ctor.call_count == 2
        mock_ctor.assert_any_call("all-MiniLM-L6-v2", device="cpu", local_files_only=True)
        mock_ctor.assert_any_call("all-MiniLM-L6-v2", device="cpu")
    finally:
        embedding_service_module._model = original_model


def test_semantic_search_finds_a_real_persisted_episode_by_embedding_similarity():
    svc = EmbeddingService()
    symbol = f"EMBEDTEST{uuid4().hex[:6]}"
    features = {"RSI": 22.0, "ATR": 2.1, "volatility": 0.05}

    episode = Episode(
        id=uuid4(),
        symbol=symbol,
        observation={"features": features},
        binding_expression="oversold-breakout",
        decision="LONG",
        outcome={"pnl": 120.0},
        lesson="oversold RSI + high volatility preceded a LONG win",
    )
    embedding = svc.encode_episode(episode.model_dump(mode="json"))

    with SessionFactory.get_session() as session:
        EpisodeRepository(session).save(episode, embedding=embedding)

    results = SemanticSearch().find_similar_episodes(features, symbol=symbol, limit=5)

    assert len(results) >= 1
    assert results[0]["episode_id"] == str(episode.id)
    assert results[0]["symbol"] == symbol
    # encode_episode() (symbol+decision+expression+features) and
    # encode_features() (symbol+features only) embed different text for the
    # same underlying features, so this isn't a bit-identical self-match —
    # just meaningfully similar (real cosine similarity, not a placeholder).
    assert results[0]["similarity"] > 0.7
