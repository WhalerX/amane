from unittest.mock import AsyncMock

import pytest

from amane.crawlers.http import HttpClient
from amane.crawlers.sites.getchu import GetchuCrawler

PRODUCT_HTML = """
<html>
  <head>
    <meta property="og:image" content="/brandnew/1364145/c1364145package.jpg">
  </head>
  <body>
    <nav>
      <a href="/genre.html">R18</a>
      <a href="/rank/genre.html">セールスランキング</a>
    </nav>
    <h2 id="soft-title">ヌきヌき ずっぽしイズム 後編[ドラチェフ]</h2>
    <table id="soft_table">
      <tr><td>ブランド：</td><td><a>Queen Bee</a></td></tr>
      <tr><td>発売日：</td><td>2026/07/10</td></tr>
      <tr><td>品番：</td><td>QNB-M185</td></tr>
      <tr>
        <td>サブジャンル：</td>
        <td>
          <a href="/all/genre.html?sub_genre_id=348">アダルトコミック原作アニメ</a>
          <a href="/all/genre.html?sub_genre_id=336">アダルトアニメ</a>
          <a href="/php/sub_genre.phtml">[一覧]</a>
        </td>
      </tr>
    </table>
    <a class="highslide" href="/brandnew/1364145/c1364145package.jpg">
      <img src="/brandnew/1364145/rc1364145package.jpg">
    </a>
    <a class="highslide" href="/brandnew/1364145/c1364145sample1.jpg">
      <img src="/brandnew/1364145/c1364145sample1_s.jpg">
    </a>
    <a class="highslide" href="/brandnew/1364145/c1364145sample2.jpg">
      <img src="/brandnew/1364145/c1364145sample2_s.jpg">
    </a>
    <h3 class="tabletitle">ストーリー</h3>
    <div class="tablebody"><b>作品紹介</b><br>剧情第一段。<br>剧情第二段。</div>
    <video><source src="https://media.example/trailer.mp4"></video>
  </body>
</html>
"""


def _crawler() -> GetchuCrawler:
    web = AsyncMock()
    web.get_text.return_value = PRODUCT_HTML
    return GetchuCrawler(client=HttpClient(web=web))


@pytest.mark.asyncio
async def test_scrape_extracts_product_images_genres_and_trailer() -> None:
    crawler = _crawler()
    result = await crawler._scrape("https://www.getchu.com/item/1364145/")

    assert result is not None
    assert result.number == "QNB-M185"
    assert result.title == "ヌきヌき ずっぽしイズム 後編[ドラチェフ]"
    assert result.release == "2026-07-10"
    assert result.studio == "Queen Bee"
    assert result.plot == "作品紹介 剧情第一段。 剧情第二段。"
    assert result.tags == ["アダルトコミック原作アニメ", "アダルトアニメ"]
    assert result.thumb_urls == ["https://www.getchu.com/brandnew/1364145/c1364145package.jpg"]
    assert result.extrafanart == [
        "https://www.getchu.com/brandnew/1364145/c1364145sample1.jpg",
        "https://www.getchu.com/brandnew/1364145/c1364145sample2.jpg",
    ]
    assert result.trailer_urls == ["https://media.example/trailer.mp4"]


def test_profile_declares_same_origin_referer_for_image_requests() -> None:
    assert GetchuCrawler.profile().same_origin_referer
