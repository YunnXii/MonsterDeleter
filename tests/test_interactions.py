import random

from app.interactions import RandomQuipProvider


def test_interaction_provider_uses_repeat_pool_after_repeated_clicks() -> None:
    provider = RandomQuipProvider(rng=random.Random(7))

    normal = provider.next_message(1)
    repeated = provider.next_message(3)
    very_repeated = provider.next_message(6)

    assert normal in provider.NORMAL
    assert repeated in provider.REPEAT
    assert very_repeated in provider.VERY_REPEAT


def test_interaction_provider_avoids_immediate_duplicate_when_possible() -> None:
    provider = RandomQuipProvider(rng=random.Random(2))
    first = provider.next_message(1)
    second = provider.next_message(1)

    assert first != second
