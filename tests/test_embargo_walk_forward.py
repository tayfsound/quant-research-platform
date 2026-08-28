"""backtest/embargo_walk_forward.py testleri — daha önce HİÇ test kapsamı
yoktu (kullanıcı isteği: "embargo_walk_forward.py kontrolünü atlamayalım").

Kod incelemesiyle doğrulandı: meta_optimizer/agent_tuner.py::walk_forward_
validate'deki tek gerçek kullanım, her kaydın feature'larını CANLI decision
anındaki gerçek market_snapshot'tan (retrospektif lookback yeniden
hesaplaması OLMADAN) alıyor — bu yüzden bu dosyanın TEK sorumluluğu, train/
test arasında train_end ile test_start arasında TAM `embargo` kadar bir
boşluk bırakan, asla örtüşmeyen fold indeksleri üretmek. Bu dosya bu
invaryantı hem birim hem (Hypothesis ile) geniş rastgele girdi uzayında
kanıtlıyor."""
from hypothesis import given, settings
from hypothesis import strategies as st

from backtest.embargo_walk_forward import EmbargoWalkForwardSplitter, WalkForwardSplit


def test_train_size_zero_or_negative_raises():
    for bad in (0, -1):
        try:
            EmbargoWalkForwardSplitter(train_size=bad, test_size=10, step=10)
            assert False, "beklenen ValueError fırlatılmadı"
        except ValueError:
            pass


def test_test_size_zero_or_negative_raises():
    for bad in (0, -1):
        try:
            EmbargoWalkForwardSplitter(train_size=10, test_size=bad, step=10)
            assert False, "beklenen ValueError fırlatılmadı"
        except ValueError:
            pass


def test_step_zero_or_negative_raises():
    for bad in (0, -1):
        try:
            EmbargoWalkForwardSplitter(train_size=10, test_size=10, step=bad)
            assert False, "beklenen ValueError fırlatılmadı"
        except ValueError:
            pass


def test_negative_embargo_raises():
    try:
        EmbargoWalkForwardSplitter(train_size=10, test_size=10, step=10, embargo=-1)
        assert False, "beklenen ValueError fırlatılmadı"
    except ValueError:
        pass


def test_zero_embargo_leaves_no_gap_between_train_and_test():
    splitter = EmbargoWalkForwardSplitter(train_size=10, test_size=5, step=10, embargo=0)
    splits = splitter.split(n_bars=20)
    assert len(splits) == 1
    assert splits[0] == WalkForwardSplit(train_start=0, train_end=10, test_start=10, test_end=15)


def test_embargo_creates_an_exact_gap_between_train_end_and_test_start():
    splitter = EmbargoWalkForwardSplitter(train_size=10, test_size=5, step=10, embargo=3)
    splits = splitter.split(n_bars=20)
    assert len(splits) == 1
    split = splits[0]
    assert split.test_start - split.train_end == 3
    # embargo aralığındaki [train_end, test_start) indeksleri NE train'de
    # NE test'te — ikisinden de dışlanmış olmalı.
    embargoed_indices = set(range(split.train_end, split.test_start))
    train_indices = set(range(split.train_start, split.train_end))
    test_indices = set(range(split.test_start, split.test_end))
    assert embargoed_indices.isdisjoint(train_indices)
    assert embargoed_indices.isdisjoint(test_indices)


def test_insufficient_bars_produces_no_splits():
    splitter = EmbargoWalkForwardSplitter(train_size=100, test_size=50, step=50, embargo=10)
    assert splitter.split(n_bars=50) == []


def test_no_split_ever_reads_past_n_bars():
    splitter = EmbargoWalkForwardSplitter(train_size=10, test_size=5, step=7, embargo=2)
    n_bars = 43
    splits = splitter.split(n_bars=n_bars)
    assert len(splits) > 0  # birden çok fold üretecek şekilde seçildi
    for split in splits:
        assert split.test_end <= n_bars


def test_step_controls_fold_advancement():
    splitter = EmbargoWalkForwardSplitter(train_size=10, test_size=5, step=5, embargo=0)
    splits = splitter.split(n_bars=30)
    starts = [s.train_start for s in splits]
    assert starts == sorted(starts)
    for a, b in zip(starts, starts[1:]):
        assert b - a == 5


@given(
    train_size=st.integers(min_value=1, max_value=50),
    test_size=st.integers(min_value=1, max_value=50),
    step=st.integers(min_value=1, max_value=50),
    embargo=st.integers(min_value=0, max_value=20),
    n_bars=st.integers(min_value=0, max_value=300),
)
@settings(max_examples=300)
def test_train_and_test_never_overlap_and_gap_is_always_exactly_embargo(
    train_size, test_size, step, embargo, n_bars
):
    """Bu splitter'ın VAROLUŞ SEBEBİ olan invaryant: HER üretilen fold'da
    train ve test kümeleri asla kesişmez, ve aralarında TAM `embargo` kadar
    (ne fazla ne eksik) bir boşluk vardır — geniş, rastgele bir
    (train_size, test_size, step, embargo, n_bars) uzayında kanıtlanıyor."""
    splitter = EmbargoWalkForwardSplitter(
        train_size=train_size, test_size=test_size, step=step, embargo=embargo
    )
    for split in splitter.split(n_bars=n_bars):
        assert split.train_start < split.train_end
        assert split.test_start < split.test_end
        assert split.test_start - split.train_end == embargo
        train_indices = set(range(split.train_start, split.train_end))
        test_indices = set(range(split.test_start, split.test_end))
        assert train_indices.isdisjoint(test_indices)
        assert split.test_end <= n_bars
        assert split.train_start >= 0


@given(
    train_size=st.integers(min_value=1, max_value=50),
    test_size=st.integers(min_value=1, max_value=50),
    step=st.integers(min_value=1, max_value=50),
    embargo=st.integers(min_value=0, max_value=20),
    n_bars=st.integers(min_value=0, max_value=300),
)
@settings(max_examples=200)
def test_no_generated_fold_can_be_extended_by_one_more_step_within_bounds(
    train_size, test_size, step, embargo, n_bars
):
    """split() n_bars'ı aşan bir sonraki fold'u ASLA döndürmemeli — son
    fold'dan bir `step` sonrası hâlâ n_bars içine sığıyorsa, bu bir eksik-
    üretim (fail-open, gerçek OOS fold'ları sessizce atlama) bug'ı olurdu."""
    splitter = EmbargoWalkForwardSplitter(
        train_size=train_size, test_size=test_size, step=step, embargo=embargo
    )
    splits = splitter.split(n_bars=n_bars)
    next_train_start = (splits[-1].train_start + step) if splits else 0
    next_test_end = next_train_start + train_size + embargo + test_size
    assert next_test_end > n_bars
