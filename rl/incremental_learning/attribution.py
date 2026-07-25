"""Trade kazanç/kayıp atıf analizi."""

class TradeAttribution:
    @staticmethod
    def analyze(features: dict[str, float], feature_importance: dict[str, float]) -> dict:
        """Hangi özellikler kazandırdı/kaybettirdi?"""
        contributions = {}
        for name, value in features.items():
            importance = feature_importance.get(name, 0.0)
            contributions[name] = value * importance
        sorted_contrib = sorted(contributions.items(), key=lambda x: abs(x[1]), reverse=True)
        return {
            "top_contributors": sorted_contrib[:5],
            "feature_count": len(features),
        }
