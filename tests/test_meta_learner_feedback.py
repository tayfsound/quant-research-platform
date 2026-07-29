from services.meta_learner import MetaLearner


def test_meta_learner_improves_threshold_from_reward():
    learner = MetaLearner()

    for _ in range(50):
        learner.record_cycle(
            confidence=0.85,
            was_correct=True,
            reward=1.0,
        )

    params = learner.suggest_parameters(
        {
            "act_threshold": 0.7,
            "reduce_threshold": 0.4,
        },
        window=50,
    )

    assert params["act_threshold"] > 0.6
    assert params["reduce_threshold"] > 0.25
