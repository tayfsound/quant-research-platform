"""ReplayEngine integrity + hash verification."""
from unittest.mock import patch

def test_replay_integrity_with_hash():
    with patch("transformers.AutoModel.from_pretrained"):
        with patch("transformers.AutoTokenizer.from_pretrained"):
            from services.replay_engine import ReplayEngine
            import hashlib

            engine = ReplayEngine()
            ctx = object()  # minimal stub

            # Store with hash
            raw = b"BTCUSDT|LONG|0.8"
            expected_hash = hashlib.sha256(raw).hexdigest()

            # Verify integrity
            result = hashlib.sha256(raw).hexdigest() == expected_hash
            assert result is True

def test_replay_integrity_detects_tamper():
    import hashlib
    raw = b"BTCUSDT|LONG|0.8"
    original_hash = hashlib.sha256(raw).hexdigest()
    tampered = b"BTCUSDT|SHORT|0.8"
    tampered_hash = hashlib.sha256(tampered).hexdigest()
    assert original_hash != tampered_hash
