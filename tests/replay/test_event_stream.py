from services.replay.event_stream import ReplayEventStream


def test_event_stream():

    stream = ReplayEventStream([
        {"id": 1},
        {"id": 2},
    ])

    assert stream.count() == 2
    assert list(stream)[0]["id"] == 1
