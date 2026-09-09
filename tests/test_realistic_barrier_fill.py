"""Faz 477 — stop aşımının kök nedeni ve düzeltmesi.

Kullanıcı: "Gerçek nedenini ölçelim, stop aşımını olabildiğince
durduralım." Ölçüm sonucu: `close_due_positions()` tek bir 1dk mumun
`close`'unu HEM tetik kontrolü HEM dolum fiyatı olarak kullanıyordu.
Gerçek veride (3 gün, n=470) medyan aşım fiyatın %0,078'i, P90 %0,692'si
— tipik bir 1dk mum aralığı kadar, yani aşım piyasa hareketinden değil
ÖRNEKLEME YÖNTEMİNDEN geliyordu.
"""
from dataclasses import dataclass

from services.position_closer import realistic_barrier_fill


@dataclass
class _Bar:
    open: float
    high: float
    low: float
    close: float


def test_long_stop_fills_at_the_stop_not_at_the_much_lower_close():
    """ASIL DÜZELTME. Stop 100; mum 101 açılıp 95'e inip 93 kapanıyor.

    ESKİ davranış: 93'ten kapatılırdı -> stop mesafesine göre devasa
    yapay aşım. Borsada duran bir stop emri 100'de gerçekleşirdi."""
    fill = realistic_barrier_fill("LONG", _Bar(101, 101, 95, 93), 100.0, 120.0)
    assert fill == 100.0


def test_short_stop_fills_at_the_stop():
    fill = realistic_barrier_fill("SHORT", _Bar(99, 107, 99, 106), 100.0, 80.0)
    assert fill == 100.0


def test_a_real_gap_is_NOT_papered_over():
    """Mum stop'un ÖTESİNDE açtıysa gerçek bir boşluk vardır — o kaymayı
    yok saymak uydurma iyimserlik olurdu. Dolum AÇILIŞTA."""
    # LONG, stop 100, mum 96'dan ACILIYOR (gecede bosluk)
    assert realistic_barrier_fill("LONG", _Bar(96, 97, 94, 95), 100.0, 120.0) == 96.0
    # SHORT, stop 100, mum 104'ten aciliyor
    assert realistic_barrier_fill("SHORT", _Bar(104, 106, 103, 105), 100.0, 80.0) == 104.0


def test_intrabar_touch_is_detected_even_when_close_recovers():
    """ESKİ KODUN İKİNCİ KUSURU: fiyat mum içinde stop'a değip toparlarsa
    `close` kontrolü bunu HİÇ görmüyordu (yanlış negatif). Gerçekte
    borsadaki stop emri çoktan tetiklenmiş olurdu."""
    # Stop 100; low 99 (degdi) ama close 105 (toparladi)
    assert realistic_barrier_fill("LONG", _Bar(104, 106, 99, 105), 100.0, 130.0) == 100.0


def test_take_profit_also_fills_at_the_barrier():
    assert realistic_barrier_fill("LONG", _Bar(101, 125, 100, 118), 90.0, 120.0) == 120.0
    assert realistic_barrier_fill("SHORT", _Bar(99, 100, 75, 82), 110.0, 80.0) == 80.0


def test_stop_wins_when_both_barriers_are_touched_in_the_same_bar():
    """Mum içi sıralamayı BİLEMEYİZ; muhafazakâr olan kötü senaryodur.
    Aksi halde simülasyon kendini sistematik olarak kandırırdı."""
    # LONG: hem stop (low 95 <= 100) hem hedef (high 125 >= 120) degdi
    assert realistic_barrier_fill("LONG", _Bar(105, 125, 95, 110), 100.0, 120.0) == 100.0


def test_returns_none_when_no_barrier_is_touched():
    """Tetiklenmediyse çağıran taraf normal `close` ile devam etmeli —
    davranış DEĞİŞMEMELİ."""
    assert realistic_barrier_fill("LONG", _Bar(105, 108, 102, 106), 100.0, 120.0) is None


def test_fails_closed_on_a_bar_without_ohlc():
    """low/high taşımayan bir veri kaynağında uydurma bir dolum
    üretilmez — çağıran eski davranışa düşer."""
    class _Partial:
        close = 93.0

    assert realistic_barrier_fill("LONG", _Partial(), 100.0, 120.0) is None


def test_missing_barrier_levels_are_handled():
    assert realistic_barrier_fill("LONG", _Bar(101, 105, 95, 96), None, None) is None
    # Sadece hedef tanimliysa stop kontrolu atlanir.
    assert realistic_barrier_fill("LONG", _Bar(101, 125, 95, 118), None, 120.0) == 120.0
