from services.training_feature_extractor import TrainingFeatureExtractor


def test_extract_training_features():
    extractor = TrainingFeatureExtractor()

    features = extractor.extract(
        {
            "confidence": 0.8,
            "size": 1.5,
            "pnl": 120,
            "agent_contributions": [
                {"domain": "technical"},
                {"domain": "macro"},
            ],
        }
    )

    assert features.confidence == 0.8
    assert features.size == 1.5
    assert features.agent_count == 2
    assert features.label == 1
