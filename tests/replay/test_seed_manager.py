from services.replay.seed_manager import ReplaySeedManager


def test_seed_is_deterministic():

    manager = ReplaySeedManager()

    manager.set_seed(42)
    first = manager.generate()

    manager.set_seed(42)
    second = manager.generate()

    assert first == second
