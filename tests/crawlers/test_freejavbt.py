from unittest.mock import AsyncMock

import pytest

from amane.crawlers.http import HttpClient
from amane.crawlers.models import SearchQuery
from amane.crawlers.sites.freejavbt import FreejavbtCrawler
from amane.parsing.file_info import ContentType


@pytest.mark.asyncio
async def test_search_matches_name_with_trailing_release_year_and_scrapes_detail() -> None:
    web = AsyncMock()
    web.get_text.side_effect = (
        """
        <div class="category-page video-list-item">
          <a href="https://freejavbt.com/en/EDUCATINGMANDY-1985">Educating Mandy</a>
        </div>
        """,
        """
        <main>
          <h1 class="text-white">EDUCATINGMANDY-1985</h1>
          <video poster="https://img.example/educating-mandy.jpg"></video>
        </main>
        """,
    )
    crawler = FreejavbtCrawler(client=HttpClient(web=web))

    result = await crawler.fetch(SearchQuery("EDUCATINGMANDY", content_type=ContentType.WESTERN))

    assert result is not None
    assert result.number == "EDUCATINGMANDY-1985"
    assert result.title == "EDUCATINGMANDY-1985"
    assert result.source_url == "https://freejavbt.com/en/EDUCATINGMANDY-1985"
    assert result.thumb_urls == ["https://img.example/educating-mandy.jpg"]
    assert web.get_text.await_args_list[0].args[0] == "https://freejavbt.com/search/EDUCATINGMANDY"
    assert web.get_text.await_args_list[1].args[0] == "https://freejavbt.com/en/EDUCATINGMANDY-1985"


@pytest.mark.asyncio
async def test_search_does_not_match_a_different_title_with_trailing_year() -> None:
    web = AsyncMock()
    web.get_text.return_value = """
    <div class="category-page video-list-item">
      <a href="https://freejavbt.com/en/DIFFERENTMANDY-1985">Different title</a>
    </div>
    """
    crawler = FreejavbtCrawler(client=HttpClient(web=web))

    result = await crawler._search(SearchQuery("EDUCATINGMANDY", content_type=ContentType.WESTERN))

    assert result is None
