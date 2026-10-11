from urllib.parse import quote_plus, urljoin

from parsel import Selector

from ...enums import SiteName
from ..base import Crawler, CrawlerProfile
from ..models import FetchOptions, MediaMetadata, SearchQuery
from ..parsing import extract_all_texts, extract_text, leading_token


class GetchuCrawler(Crawler):
    @classmethod
    def profile(cls) -> CrawlerProfile:
        return CrawlerProfile(
            name=SiteName.GETCHU,
            base_url="https://www.getchu.com",
            cookies={"getchu_adalt_flag": "getchu.com", "gc": "gc"},
            same_origin_referer=True,
        )

    async def _search(self, query: SearchQuery, options: FetchOptions | None = None) -> str | None:
        number = query.number
        search_url = f"{self.base_url}/php/nsearch.phtml?search_keyword={quote_plus(number)}&gc=gc"
        text = await self.client.get_html(search_url, cookies=self.cookies, encoding="euc_jp")
        if not text:
            return None

        html = Selector(text=text)
        results = html.xpath('//a[contains(@href,"soft.phtml")]/@href').getall()
        urls = [urljoin(self.base_url, r) for r in results]
        return urls[0] if urls else None

    async def _scrape(self, url: str, options: FetchOptions | None = None) -> MediaMetadata | None:
        text = await self.client.get_html(url, cookies=self.cookies, encoding="euc_jp")
        if not text:
            return None

        html = Selector(text=text)

        title = extract_text(html, '//h2[@id="soft-title"]/text()', '//h1[@id="soft-title"]/text()')
        if not title:
            return None

        cover = extract_text(
            html,
            '//meta[@property="og:image"]/@content',
            '//a[contains(concat(" ", normalize-space(@class), " "), " highslide ")][contains(@href,"package")]/@href',
            '//table[@id="soft_table"]//img[contains(@src,"package")]/@src',
            '//img[@class="product_img"]/@src',
        )
        if cover and not cover.startswith("http"):
            cover = urljoin(url, cover)

        extrafanart = extract_all_texts(
            html,
            '//a[contains(concat(" ", normalize-space(@class), " "), " highslide ")][contains(@href,"sample")]/@href',
        )
        extrafanart = [urljoin(url, image) for image in extrafanart]

        release = extract_text(
            html,
            'string(//td[contains(normalize-space(.),"発売日")]/following-sibling::td[1])',
        )
        studio = extract_text(
            html,
            '//td[contains(normalize-space(.),"ブランド")]/following-sibling::td[1]/a[1]/text()',
        )
        plot_parts = extract_all_texts(
            html,
            '//h3[contains(@class,"tabletitle") and normalize-space(.)="ストーリー"]/following-sibling::div[contains(@class,"tablebody")][1]//text()[normalize-space()]',
        )
        plot = " ".join(" ".join(plot_parts).split())
        tags = extract_all_texts(
            html,
            '//td[contains(normalize-space(.),"サブジャンル")]/following-sibling::td[1]/a[not(contains(normalize-space(.),"一覧"))]/text()',
        )
        trailer = extract_text(html, "//video/source/@src", "//video/@src")

        number = extract_text(
            html,
            'string(//td[contains(normalize-space(.),"品番")]/following-sibling::td[1])',
        ) or leading_token(title)

        return MediaMetadata(
            number=number,
            title=title,
            studio=studio or None,
            release=release or None,
            plot=plot or None,
            tags=tags,
            thumb_urls=[cover] if cover else [],
            trailer_urls=[urljoin(url, trailer)] if trailer else [],
            extrafanart=extrafanart,
            source_url=url,
        )
