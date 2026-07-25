import httpx
from app.core.security import decode_access_token
from app.modules.identity.models import User


def test_user_factory_fixture(user_factory: object) -> None:
    user = user_factory(email="fixture@example.com")

    assert isinstance(user, User)
    assert user.email == "fixture@example.com"


def test_auth_header_fixture(auth_header: dict[str, str]) -> None:
    scheme, token = auth_header["Authorization"].split(" ", 1)
    claims = decode_access_token(token)

    assert scheme == "Bearer"
    assert claims.token_version == 1


async def test_app_client_fixture(app_client: httpx.AsyncClient) -> None:
    response = await app_client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

