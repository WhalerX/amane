from unittest.mock import AsyncMock

import pytest

from amane.config import SiteConfig
from amane.crawlers.http import HttpClient
from amane.crawlers.models import SearchQuery
from amane.crawlers.sites.theporndb import ThePornDBCrawler
from amane.parsing.file_info import ContentType

_NUMBER = "mariosalieriproductions.18.09.07"
_MOVIE = {
    "id": "fa042f97-691a-422f-8e2a-c57b1d541bf5",
    "slug": "mariosalieriproductions-sceneggiata-napoletana",
    "title": "Sceneggiata Napoletana",
    "date": "2018-09-07",
    "site": {"name": "Mario Salieri Productions"},
}
_MOVIE_URL = "https://theporndb.net/movies/mariosalieriproductions-sceneggiata-napoletana"
_MOVIE_API_DETAIL_URL = "https://api.theporndb.net/movies/fa042f97-691a-422f-8e2a-c57b1d541bf5"


def _crawler(
    *responses: dict[str, object],
    movie_responses: tuple[dict[str, object], ...] = (),
) -> tuple[ThePornDBCrawler, AsyncMock]:
    web = AsyncMock()
    web.post_json.side_effect = responses
    web.get_json.side_effect = movie_responses
    crawler = ThePornDBCrawler(
        client=HttpClient(web=web),
        config=SiteConfig(api_token="test-token"),
    )
    return crawler, web


@pytest.mark.asyncio
async def test_fetch_falls_back_to_movies_after_scene_lookup_misses() -> None:
    crawler, web = _crawler(
        {"data": {"searchScene": []}},
        movie_responses=(
            {"data": [_MOVIE]},
            {
                "data": {
                    **_MOVIE,
                    "description": "A full-length description.",
                    "poster": "https://img.example/poster.jpg",
                }
            },
        ),
    )

    result = await crawler.fetch(SearchQuery(_NUMBER, content_type=ContentType.WESTERN))

    assert result is not None
    assert result.title == "Sceneggiata Napoletana"
    assert result.source_url == _MOVIE_URL
    assert result.number == _NUMBER
    assert result.studio == "Mario Salieri Productions"
    assert result.plot == "A full-length description."
    assert result.poster_urls == ["https://img.example/poster.jpg"]
    assert "searchScene" in web.post_json.call_args.kwargs["json"]["query"]
    movie_calls = web.get_json.call_args_list
    assert movie_calls[0].args[0] == (
        "https://api.theporndb.net/movies?parse=mariosalieriproductions.18.09.07&hash=&year="
    )
    assert movie_calls[1].args[0] == _MOVIE_API_DETAIL_URL
    assert movie_calls[0].kwargs["headers"] == {
        "Authorization": "Bearer test-token",
        "Accept": "application/json",
    }


@pytest.mark.asyncio
async def test_search_and_scrape_keep_scene_route_for_scene_matches() -> None:
    scene = {
        "id": "fansdbgattouz0onlyfans-gattouz0-2026-02-22",
        "title": "Gattouz0",
        "code": "Fansdbgattouz0onlyfans:Gattouz0",
        "date": "2026-02-22",
        "studio": {"name": "Fansdb Gattouz0 OnlyFans"},
    }
    crawler, web = _crawler(
        {"data": {"searchScene": [scene]}},
        {"data": {"findScene": scene}},
    )

    url = await crawler._search(SearchQuery("Fansdbgattouz0onlyfans.26.02.22", content_type=ContentType.WESTERN))
    assert url == "gql://scene/fansdbgattouz0onlyfans-gattouz0-2026-02-22"

    result = await crawler._scrape(url)

    assert result is not None
    assert result.source_url == ("https://theporndb.net/scenes/fansdbgattouz0onlyfans-gattouz0-2026-02-22")
    assert web.post_json.call_args_list[1].args[0] == "https://theporndb.net/graphql"
    assert "findScene" in web.post_json.call_args_list[1].kwargs["json"]["query"]


@pytest.mark.asyncio
async def test_search_and_scrape_use_movie_route_for_movie_matches() -> None:
    crawler, web = _crawler(
        {"data": {"searchScene": []}},
        movie_responses=(
            {"data": [_MOVIE]},
            {"data": _MOVIE},
        ),
    )

    url = await crawler._search(SearchQuery(_NUMBER, content_type=ContentType.WESTERN))

    assert url is not None
    assert url == ("api://movie/fa042f97-691a-422f-8e2a-c57b1d541bf5?number=mariosalieriproductions.18.09.07")
    result = await crawler._scrape(url)

    assert result is not None
    assert result.source_url == _MOVIE_URL
    assert result.number == _NUMBER
    calls = web.get_json.call_args_list
    assert calls[0].args[0] == ("https://api.theporndb.net/movies?parse=mariosalieriproductions.18.09.07&hash=&year=")
    assert calls[1].args[0] == _MOVIE_API_DETAIL_URL


@pytest.mark.asyncio
async def test_western_movie_lookup_rejects_unmatched_results() -> None:
    crawler, web = _crawler(
        {"data": {"searchScene": []}},
        movie_responses=({"data": [{**_MOVIE, "date": "2018-09-08"}]},),
    )

    result = await crawler.fetch(SearchQuery(_NUMBER, content_type=ContentType.WESTERN))

    assert result is None
    assert web.post_json.await_count == 1
    assert web.get_json.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [{}, {"data": None}, {"data": "invalid"}])
async def test_western_movie_lookup_ignores_invalid_api_response_shapes(
    response: dict[str, object],
) -> None:
    crawler, web = _crawler(
        {"data": {"searchScene": []}},
        movie_responses=(response,),
    )

    result = await crawler.fetch(SearchQuery(_NUMBER, content_type=ContentType.WESTERN))

    assert result is None
    assert web.get_json.await_count == 1


@pytest.mark.asyncio
async def test_task_218_movie_search_ignores_file_hash_and_uses_the_api_slug() -> None:
    number = "Mariosalieriproductions.18.09.07"
    file_hash = "5b2dc3a7a16565f4"
    crawler, web = _crawler(
        {"data": {"findScenesBySceneFingerprints": [[]]}},
        {"data": {"searchScene": []}},
        movie_responses=(
            {
                "data": [
                    {**_MOVIE, "date": "1994-01-01", "site": {"name": "The Classic Porn"}},
                    _MOVIE,
                    {**_MOVIE, "date": "2009-11-26", "title": "Sceneggiata Napoletana (German)"},
                ]
            },
            {
                "data": {
                    **_MOVIE,
                    "description": "Sceneggiata Napoletana Video On Demand From Mario Salieri Productions.",
                    "poster": "https://cdn.theporndb.net/poster.jpg",
                    "duration": 5770,
                }
            },
        ),
    )

    result = await crawler.fetch(SearchQuery(number, file_hash=file_hash, content_type=ContentType.WESTERN))

    assert result is not None
    assert result.number == number
    assert result.title == "Sceneggiata Napoletana"
    assert result.source_url == _MOVIE_URL
    assert result.release == "2018-09-07"
    assert result.studio == "Mario Salieri Productions"
    assert result.runtime == 96
    assert result.plot.startswith("Sceneggiata Napoletana")
    assert result.poster_urls == ["https://cdn.theporndb.net/poster.jpg"]
    fingerprint_request = web.post_json.call_args_list[0].kwargs["json"]
    assert "findScenesBySceneFingerprints" in fingerprint_request["query"]
    assert fingerprint_request["variables"] == {
        "fingerprints": [[{"hash": file_hash, "algorithm": "OSHASH"}]],
    }
    movie_requests = web.get_json.call_args_list
    assert movie_requests[0].args[0] == (
        "https://api.theporndb.net/movies?parse=Mariosalieriproductions.18.09.07&hash=&year="
    )
    assert movie_requests[0].kwargs["headers"] == {
        "Authorization": "Bearer test-token",
        "Accept": "application/json",
    }
    assert movie_requests[1].args[0] == _MOVIE_API_DETAIL_URL


@pytest.mark.asyncio
async def test_movie_images_use_large_variants_from_the_api() -> None:
    crawler, _ = _crawler(
        {"data": {"searchScene": []}},
        movie_responses=(
            {"data": [_MOVIE]},
            {
                "data": {
                    **_MOVIE,
                    "posters": {"large": "https://img.example/poster-large.jpg"},
                    "background": {"large": "https://img.example/background-large.jpg"},
                    "background_back": {"large": "https://img.example/background-back-large.jpg"},
                }
            },
        ),
    )

    result = await crawler.fetch(SearchQuery(_NUMBER, content_type=ContentType.WESTERN))

    assert result is not None
    assert result.poster_urls == ["https://img.example/poster-large.jpg"]
    assert result.thumb_urls == ["https://img.example/background-large.jpg"]
    assert result.extrafanart == ["https://img.example/background-back-large.jpg"]


@pytest.mark.asyncio
async def test_movie_images_fall_back_to_available_variants_and_legacy_poster() -> None:
    crawler, _ = _crawler(
        {"data": {"searchScene": []}},
        movie_responses=(
            {"data": [_MOVIE]},
            {
                "data": {
                    **_MOVIE,
                    "poster": "https://img.example/poster.jpg",
                    "posters": {"large": None, "full": ""},
                    "background": {"large": None, "full": "https://img.example/background-full.jpg"},
                    "background_back": {"large": None, "full": None},
                }
            },
        ),
    )

    result = await crawler.fetch(SearchQuery(_NUMBER, content_type=ContentType.WESTERN))

    assert result is not None
    assert result.poster_urls == ["https://img.example/poster.jpg"]
    assert result.thumb_urls == ["https://img.example/background-full.jpg"]
    assert result.extrafanart == []
