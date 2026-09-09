"""Shared test helper: create a user with a specific role and a matching
bearer token, bypassing the API's first-user-is-admin bootstrap (which is
order-dependent across a shared test DB — direct repository creation is
deterministic regardless of test execution order)."""
from contracts.auth import Role, User
from database.repositories.auth_repository import UserRepository
from database.session_factory import SessionFactory
from services.auth_service import create_access_token, hash_password


def make_authed_headers(role: Role = Role.ADMIN) -> dict[str, str]:
    """Faz 475 — KULLANICI ADI ARTIK DETERMİNİSTİK (rol başına TEK kullanıcı).

    Eskiden her çağrı `uuid4()` ile YENİ bir kullanıcı yaratıyordu ve bu
    satırlar hiç silinmiyordu: quantdb_test'te 3.911 `test_*` kullanıcı
    birikmişti (kök conftest.py'nin session-başı TRUNCATE'i `users`
    tablosunu KASITLI koruyor, çünkü boş kalırsa sistem sessizce bozulur).

    uuid'nin gerekçesi "paylaşımlı test DB'sinde sıra bağımsızlığı"ydı —
    ama rol başına SABİT bir kullanıcı adı da aynı determinizmi veriyor
    (ilk-kullanıcı-admin bootstrap'i yine baypas ediliyor, çünkü kullanıcı
    doğrudan repository'den yaratılıyor) ve sınırsız büyüme olmuyor.

    Varsa mevcut kullanıcı tekrar kullanılıyor; yoksa bir kez yaratılıyor."""
    username = f"test_{role.name.lower()}"
    with SessionFactory.get_session() as session:
        repo = UserRepository(session)
        existing = repo.get_by_username(username)
        if existing is not None:
            return {"Authorization": f"Bearer {create_access_token(existing.id, role)}"}
        user = User(username=username, password_hash=hash_password("irrelevant-pw-123"), role=role)
        repo.create(user)

    return {"Authorization": f"Bearer {create_access_token(user.id, role)}"}
