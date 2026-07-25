"""AppContainer için temel test."""
from container import AppContainer


def test_container_singletons() -> None:
    c = AppContainer()
    # Settings aynı instance olmalı
    s1 = c.settings
    s2 = c.settings
    assert s1 is s2
    # Message bus aynı instance
    b1 = c.message_bus
    b2 = c.message_bus
    assert b1 is b2
