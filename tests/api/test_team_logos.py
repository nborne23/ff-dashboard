"""`GET /api/team-logos/{platform}/{team_id}` — the logo proxy.

Covers the three decisions that make this a separate pipeline from headshots rather
than a reuse of it: the content-type allowlist (an XSS control), the retryable 401,
and source-URL-driven invalidation.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.gridiron.config import Settings, get_settings
from backend.gridiron.db import get_session, make_engine
from backend.gridiron.models import Base, Connection, League, Team, TeamLogo
from backend.gridiron.services import credentials, team_logos
from backend.main import app

SECRET = Fernet.generate_key().decode()

LEAGUE_ID = "espn:705139273"
TEAM_ID = "l-705139273-t-4"
TEAM_KEY = f"espn:{TEAM_ID}"

VECTOR_URL = "https://g.espncdn.com/lm-static/ffl/images/default_logos/6.svg"
UPLOAD_URL = "https://mystique-api.fantasy.espn.com/apis/v1/domains/lm/images/abc-123"
SVG_BYTES = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
JPEG_BYTES = b"\xff\xd8\xff\xe0jpegdata"


@pytest.fixture
async def engine(tmp_path):
    eng = make_engine(tmp_path / "logos.db")
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
        gridiron_secret_key=SECRET,
        gridiron_team_logos_path=str(tmp_path / "team-logos"),
    )


@pytest.fixture
async def client(session_factory, settings) -> AsyncIterator[httpx.AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_settings] = lambda: settings

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client

    app.dependency_overrides.clear()


async def seed(session_factory, logo_url: str | None, logo_type: str | None = "VECTOR") -> None:
    async with session_factory() as session:
        session.add(
            Connection(
                platform="espn",
                swid_enc=credentials.encrypt(SECRET, "{ABC-123}"),
                espn_s2_enc=credentials.encrypt(SECRET, "s2-value"),
            )
        )
        session.add(
            League(
                id=LEAGUE_ID,
                platform="espn",
                platform_id="705139273",
                name="THE LEAGUE",
                season=2026,
                team_count=10,
                scoring_type="half_ppr",
                current_week=1,
            )
        )
        session.add(
            Team(
                id=TEAM_KEY,
                league_id=LEAGUE_ID,
                platform="espn",
                platform_id=TEAM_ID,
                name="Broadcom",
                manager_name="Nick",
                record_w=0,
                record_l=0,
                record_t=0,
                rank_current=1,
                rank_total=10,
                points_for=0.0,
                points_against=0.0,
                is_user_team=True,
                logo_source_url=logo_url,
                logo_type=logo_type,
            )
        )
        await session.commit()


@pytest.mark.asyncio
@respx.mock
async def test_vector_logo_is_fetched_and_served_as_svg(client, session_factory) -> None:
    await seed(session_factory, VECTOR_URL)
    respx.get(VECTOR_URL).mock(
        return_value=httpx.Response(
            200, content=SVG_BYTES, headers={"content-type": "image/svg+xml"}
        )
    )

    response = await client.get(f"/api/team-logos/espn/{TEAM_ID}")

    assert response.status_code == 200
    assert response.content == SVG_BYTES
    assert response.headers["content-type"].startswith("image/svg+xml")
    # nosniff, because one of the allowed types is markup-shaped.
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
@respx.mock
async def test_uploaded_logo_is_fetched_with_credentials(client, session_factory) -> None:
    """The whole reason this proxy exists: this host 401s an unauthenticated client, so
    the cookies have to be attached server-side."""
    await seed(session_factory, UPLOAD_URL, "CUSTOM_UPLOAD")
    route = respx.get(UPLOAD_URL).mock(
        return_value=httpx.Response(200, content=JPEG_BYTES, headers={"content-type": "image/jpg"})
    )

    response = await client.get(f"/api/team-logos/espn/{TEAM_ID}")

    assert response.status_code == 200
    assert response.content == JPEG_BYTES
    # `image/jpg` is nonstandard but is what ESPN really sends; it is stored and echoed
    # rather than normalized or guessed from the extensionless URL.
    assert response.headers["content-type"].startswith("image/jpg")
    assert "SWID=" in route.calls[0].request.headers["cookie"]


@pytest.mark.asyncio
@respx.mock
async def test_svg_from_a_non_espn_host_is_rejected(client, session_factory) -> None:
    """Design D6, an XSS control. An SVG served from our own origin can carry script
    with same-origin access, and uploaded logos are other league members' content."""
    hostile = "https://mystique-api.fantasy.espn.com/apis/v1/domains/lm/images/evil"
    await seed(session_factory, hostile, "CUSTOM_UPLOAD")
    respx.get(hostile).mock(
        return_value=httpx.Response(
            200,
            content=b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
            headers={"content-type": "image/svg+xml"},
        )
    )

    response = await client.get(f"/api/team-logos/espn/{TEAM_ID}")

    assert response.status_code == 200
    assert b"<script>" not in response.content
    assert response.content == team_logos.read_crest()


@pytest.mark.asyncio
@respx.mock
async def test_non_image_content_type_is_rejected(client, session_factory) -> None:
    await seed(session_factory, UPLOAD_URL, "CUSTOM_UPLOAD")
    respx.get(UPLOAD_URL).mock(
        return_value=httpx.Response(
            200, content=b"<html>nope</html>", headers={"content-type": "text/html"}
        )
    )

    response = await client.get(f"/api/team-logos/espn/{TEAM_ID}")

    assert response.content == team_logos.read_crest()


@pytest.mark.asyncio
@respx.mock
async def test_a_401_is_not_cached_and_a_later_success_works(client, session_factory) -> None:
    """Design D4. Expired ESPN cookies are recoverable and this app has a reconnect
    flow for them; caching the failure would blank every logo until the cache was
    cleared by hand, and reconnecting would not fix it."""
    await seed(session_factory, UPLOAD_URL, "CUSTOM_UPLOAD")
    route = respx.get(UPLOAD_URL).mock(return_value=httpx.Response(401))

    first = await client.get(f"/api/team-logos/espn/{TEAM_ID}")
    assert first.content == team_logos.read_crest()

    async with session_factory() as session:
        rows = (await session.execute(select(TeamLogo))).scalars().all()
    assert rows == [], "a 401 must not write a cache row"

    route.mock(
        return_value=httpx.Response(200, content=JPEG_BYTES, headers={"content-type": "image/jpg"})
    )
    second = await client.get(f"/api/team-logos/espn/{TEAM_ID}")
    assert second.content == JPEG_BYTES


@pytest.mark.asyncio
@respx.mock
async def test_a_team_with_no_logo_serves_the_crest_without_a_request(
    client, session_factory
) -> None:
    await seed(session_factory, None, None)

    with respx.mock(assert_all_called=False) as inner:
        response = await client.get(f"/api/team-logos/espn/{TEAM_ID}")
        assert not inner.calls

    assert response.content == team_logos.read_crest()


@pytest.mark.asyncio
@respx.mock
async def test_cached_bytes_are_served_without_a_second_request(client, session_factory) -> None:
    await seed(session_factory, VECTOR_URL)
    route = respx.get(VECTOR_URL).mock(
        return_value=httpx.Response(
            200, content=SVG_BYTES, headers={"content-type": "image/svg+xml"}
        )
    )

    await client.get(f"/api/team-logos/espn/{TEAM_ID}")
    await client.get(f"/api/team-logos/espn/{TEAM_ID}")

    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_a_changed_source_url_refetches(client, session_factory) -> None:
    """Design D5. An uploaded logo's URL carries a generated id that changes when the
    image changes, so comparing it detects a leaguemate swapping their logo exactly —
    no TTL to guess at."""
    await seed(session_factory, VECTOR_URL)
    respx.get(VECTOR_URL).mock(
        return_value=httpx.Response(
            200, content=SVG_BYTES, headers={"content-type": "image/svg+xml"}
        )
    )
    await client.get(f"/api/team-logos/espn/{TEAM_ID}")

    new_url = "https://g.espncdn.com/lm-static/ffl/images/default_logos/9.svg"
    new_bytes = b"<svg xmlns='http://www.w3.org/2000/svg' id='new'></svg>"
    respx.get(new_url).mock(
        return_value=httpx.Response(
            200, content=new_bytes, headers={"content-type": "image/svg+xml"}
        )
    )
    async with session_factory() as session:
        team = await session.get(Team, TEAM_KEY)
        team.logo_source_url = new_url
        await session.commit()

    response = await client.get(f"/api/team-logos/espn/{TEAM_ID}")

    assert response.content == new_bytes


@pytest.mark.asyncio
async def test_path_traversal_is_rejected(client, session_factory) -> None:
    await seed(session_factory, VECTOR_URL)

    response = await client.get("/api/team-logos/espn/..%2f..%2fetc%2fpasswd")

    assert response.status_code in (404, 422)
