"""`GET /api/headshots/{platform}/{player_id}.png` — disk-hit, upstream-fetch, 404-fallback,
and path-traversal-guard coverage."""

from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron.config import Settings, get_settings
from backend.gridiron.db import get_session, make_engine
from backend.gridiron.models import Base, Headshot
from backend.gridiron.services import headshots
from backend.main import app


@pytest.fixture
async def engine(tmp_path):
    eng = make_engine(tmp_path / "test.db")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        gridiron_secret_key="test-secret-key",
        gridiron_headshots_path=str(tmp_path / "headshots"),
    )


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> AsyncIterator[httpx.AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_settings] = lambda: settings

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_disk_hit_serves_existing_file_without_network(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    dest = headshots.headshot_path(settings, "espn", "12345")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"already-cached-bytes")

    with respx.mock(assert_all_called=False) as respx_mock:
        response = await client.get("/api/headshots/espn/12345.png")

    assert not respx_mock.calls
    assert response.status_code == 200
    assert response.content == b"already-cached-bytes"
    assert response.headers["cache-control"] == "public, max-age=86400, immutable"


@pytest.mark.asyncio
@respx.mock
async def test_espn_upstream_fetch_then_disk_cache(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    respx.get("https://a.espncdn.com/i/headshots/nfl/players/full/12345.png").mock(
        return_value=httpx.Response(200, content=b"real-headshot-bytes")
    )

    response = await client.get("/api/headshots/espn/12345.png")

    assert response.status_code == 200
    assert response.content == b"real-headshot-bytes"
    assert response.headers["cache-control"] == "public, max-age=86400, immutable"

    dest = headshots.headshot_path(settings, "espn", "12345")
    assert dest.is_file()
    assert dest.read_bytes() == b"real-headshot-bytes"


@pytest.mark.asyncio
@respx.mock
async def test_yahoo_upstream_fetch_uses_headshot_table_source_url(
    client: httpx.AsyncClient,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    respx.get("https://s.yimg.com/players/999.png").mock(
        return_value=httpx.Response(200, content=b"yahoo-headshot-bytes")
    )

    async with session_factory() as session:
        session.add(
            Headshot(
                platform="yahoo", player_id="999", source_url="https://s.yimg.com/players/999.png"
            )
        )
        await session.commit()

    response = await client.get("/api/headshots/yahoo/999.png")

    assert response.status_code == 200
    assert response.content == b"yahoo-headshot-bytes"

    dest = headshots.headshot_path(settings, "yahoo", "999")
    assert dest.is_file()


@pytest.mark.asyncio
async def test_yahoo_missing_headshot_row_falls_back_to_silhouette(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    with respx.mock(assert_all_called=False) as respx_mock:
        response = await client.get("/api/headshots/yahoo/no-such-player.png")

    assert not respx_mock.calls
    assert response.status_code == 200
    assert response.content == headshots.read_silhouette()

    dest = headshots.headshot_path(settings, "yahoo", "no-such-player")
    assert dest.is_file()


@pytest.mark.asyncio
@respx.mock
async def test_upstream_404_writes_silhouette_as_negative_cache(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    respx.get("https://a.espncdn.com/i/headshots/nfl/players/full/notfound.png").mock(
        return_value=httpx.Response(404)
    )

    response = await client.get("/api/headshots/espn/notfound.png")

    assert response.status_code == 200
    assert response.content == headshots.read_silhouette()

    dest = headshots.headshot_path(settings, "espn", "notfound")
    assert dest.is_file()
    assert dest.read_bytes() == headshots.read_silhouette()

    # Second request is now a disk-hit — no further upstream call needed.
    with respx.mock(assert_all_called=False) as respx_mock:
        second = await client.get("/api/headshots/espn/notfound.png")
    assert not respx_mock.calls
    assert second.status_code == 200
    assert second.content == headshots.read_silhouette()


@pytest.mark.asyncio
async def test_invalid_platform_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/headshots/madeup/123.png")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_path_traversal_player_id_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/headshots/espn/a..b.png")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_path_traversal_encoded_slash_does_not_escape_directory(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/headshots/espn/12%2F..%2F..%2Fetc%2Fpasswd.png")
    assert response.status_code in (404, 422)
