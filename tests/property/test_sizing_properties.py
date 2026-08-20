"""Faz 324 — kullanıcı isteği: "test stratejisi: contract/chaos/
property-based testler." Bu oturum boyunca tekrarlanan ilke: "AI kendi
risk tavanını genişletemez, sadece daraltabilir" — kelly_fraction() ve
cppi_exposure_multiplier() bu ilkenin sayısal temeli. Her ikisi de pure
fonksiyon (dış bağımlılık yok) — property-based test için ideal:
sonucun HER girdide [0,1] (veya CPPI için [MIN_EXPOSURE_MULTIPLIER,1])
aralığında kaldığını, asla bu sınırların dışına taşmadığını kanıtlar."""
from hypothesis import given, settings
from hypothesis import strategies as st

from risk.predictive.cppi import BREACH_PROBABILITY_THRESHOLD, MIN_EXPOSURE_MULTIPLIER, cppi_exposure_multiplier
from services.kelly_sizing import kelly_fraction

_finite_float = st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6)
_win_rate = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_positive_or_zero = st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False)


@given(win_rate=_win_rate, avg_win=_positive_or_zero, avg_loss=_positive_or_zero)
@settings(max_examples=300)
def test_kelly_fraction_always_stays_within_zero_and_one(win_rate, avg_win, avg_loss):
    f = kelly_fraction(win_rate, avg_win, avg_loss)
    assert 0.0 <= f <= 1.0


@given(avg_win=st.floats(max_value=0.0, allow_nan=False, allow_infinity=False), avg_loss=_positive_or_zero, win_rate=_win_rate)
@settings(max_examples=100)
def test_kelly_fraction_fail_closed_when_avg_win_not_positive(avg_win, avg_loss, win_rate):
    assert kelly_fraction(win_rate, avg_win, avg_loss) == 0.0


@given(avg_loss=st.floats(max_value=0.0, allow_nan=False, allow_infinity=False), avg_win=_positive_or_zero, win_rate=_win_rate)
@settings(max_examples=100)
def test_kelly_fraction_fail_closed_when_avg_loss_not_positive(avg_loss, avg_win, win_rate):
    assert kelly_fraction(win_rate, avg_win, avg_loss) == 0.0


@given(breach_probability=st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)))
@settings(max_examples=300)
def test_cppi_multiplier_never_leaves_its_bounds(breach_probability):
    """KRİTİK GÜVENLİK İNVARYANTI: çarpan asla 1.0'ı AŞMAZ (boyutu asla
    büyütmez) ve asla MIN_EXPOSURE_MULTIPLIER'ın ALTINA inmez (bu
    modülün işi tam iptal değil, sadece kısıtlı küçültme)."""
    multiplier = cppi_exposure_multiplier({"breach_probability": breach_probability})
    assert MIN_EXPOSURE_MULTIPLIER <= multiplier <= 1.0


@given(breach_probability=st.floats(min_value=0.0, max_value=BREACH_PROBABILITY_THRESHOLD, allow_nan=False, allow_infinity=False))
@settings(max_examples=100)
def test_cppi_multiplier_is_untouched_below_threshold(breach_probability):
    assert cppi_exposure_multiplier({"breach_probability": breach_probability}) == 1.0


@given(
    lower=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    higher=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=300)
def test_cppi_multiplier_is_monotonically_non_increasing_in_breach_probability(lower, higher):
    """Daha yüksek bir breach_probability, ASLA daha yüksek (daha az
    kısıtlayıcı) bir çarpan üretmemeli — risk arttıkça boyut küçülür ya
    da aynı kalır, hiçbir zaman büyümez."""
    if lower > higher:
        lower, higher = higher, lower
    m_lower = cppi_exposure_multiplier({"breach_probability": lower})
    m_higher = cppi_exposure_multiplier({"breach_probability": higher})
    assert m_higher <= m_lower + 1e-9
