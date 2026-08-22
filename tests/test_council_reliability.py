from services.council_reliability import ReliabilityAnnotator


def test_annotator():
    a = ReliabilityAnnotator()
    ops = [{"domain": "macro", "confidence": 0.8}, {"domain": "technical", "confidence": 0.6}]
    result = a.annotate(ops)
    assert "source_reliability" in result[0]
