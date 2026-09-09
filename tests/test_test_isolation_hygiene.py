"""Faz 475 — test DB'sinin sınırsız şişmesine karşı regresyon koruması.

Kullanıcı bu sorunu "bilinen flake" olarak kabul etmedi, kalıcı çözüm
istedi (memory `project_shared_test_state_bloat`). Gerçek ölçüm
(2026-09-09): quantdb_test'te **4.058 kullanıcı** (3.911'i
`make_authed_headers`'ın her çağrıda `uuid4()` ile yarattığı `test_*`)
ve **579 app_settings** satırı (DEFAULTS sadece 98 anahtar — 481'i
`agent_bench_state__<rastgele>__technical` gibi test çöpü).

Kök conftest.py'nin session-başı TRUNCATE'i bu iki tabloyu KASITLI
koruyor (boş kalırlarsa sistem sessizce bozulur), ama koruma TABLO
seviyesinde olduğu için içleri hiç temizlenmiyordu.
"""
from contracts.auth import Role
from tests.auth_helpers import make_authed_headers


def test_authed_headers_reuse_one_user_per_role():
    """KÖK NEDEN DÜZELTMESİ. Eskiden her çağrı yeni bir uuid'li kullanıcı
    yaratıyordu; 3.911 tanesi birikmişti. Artık rol başına TEK
    deterministik kullanıcı tekrar kullanılıyor.

    Bu test kırılırsa birikim geri gelmiş demektir."""
    from database.repositories.auth_repository import UserRepository
    from database.session_factory import SessionFactory

    def _admin_count() -> int:
        with SessionFactory.get_session() as session:
            return sum(
                1 for _ in [UserRepository(session).get_by_username("test_admin")]
                if _ is not None
            )

    make_authed_headers(Role.ADMIN)
    before = _admin_count()
    for _ in range(5):
        make_authed_headers(Role.ADMIN)
    assert _admin_count() == before == 1

    # Farkli roller AYRI (ama yine rol basina TEK) kullanici alir.
    make_authed_headers(Role.VIEWER)
    with SessionFactory.get_session() as session:
        repo = UserRepository(session)
        assert repo.get_by_username("test_viewer") is not None
        assert repo.get_by_username("test_admin") is not None


def test_authed_headers_still_produce_a_usable_token():
    """Determinizm uğruna yetkilendirmeyi bozmadığımızın kontrolü."""
    headers = make_authed_headers(Role.ADMIN)
    assert headers["Authorization"].startswith("Bearer ")
    assert len(headers["Authorization"]) > 20


def test_no_uuid_suffixed_users_survive_from_previous_sessions():
    """conftest'in session-başı temizliği çalışıyor mu? Bu test
    çalıştığında SADECE bu oturumda yaratılmış uuid'li kullanıcılar
    olabilir; ÖNCEKİ oturumlardan kalan olmamalı.

    Doğrudan "0 tane olmalı" diyemeyiz (aynı oturumdaki auth testleri
    kendi geçici kullanıcılarını yaratıyor olabilir), ama BİRİKMİŞ bir
    sayı (yüzlerce) kesin bir regresyon işaretidir."""
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        n = session.execute(
            text("SELECT count(*) FROM users WHERE username ~ '_[0-9a-f]{8,}$'")
        ).scalar()
    assert n < 50, f"{n} uuid'li kullanici birikmis -- conftest temizligi calismiyor"


def test_app_settings_does_not_accumulate_random_keys():
    """`agent_bench_state__<rastgele>__technical` gibi anahtarlar her
    koşuda birikiyordu (579 satır / 98 DEFAULTS)."""
    from sqlalchemy import text

    from database.repositories.app_settings_repository import DEFAULTS
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        n = session.execute(
            text("SELECT count(*) FROM app_settings WHERE key <> ALL(:keys)"),
            {"keys": list(DEFAULTS.keys())},
        ).scalar()
    assert n < 100, f"{n} DEFAULTS-disi ayar birikmis -- conftest temizligi calismiyor"


def test_cleanup_refuses_to_run_outside_the_test_database():
    """GÜVENLİK KORUMASI: temizlik gerçek `users` satırları SİLİYOR.
    conftest yanlış bir DB'ye bağlanmışsa DURMALI, sessizce üretim
    verisi silmemeli."""
    import inspect
    import pathlib

    kaynak = pathlib.Path(
        inspect.getsourcefile(make_authed_headers)
    ).parent.parent / "conftest.py"
    metin = kaynak.read_text()
    assert "current_database()" in metin
    assert "quantdb_test" in metin
    assert "RuntimeError" in metin
