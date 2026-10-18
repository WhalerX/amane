from typing import TYPE_CHECKING, Any, Literal, override
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

from ...enums import ActorGender, SiteName
from ...net.connectivity import ConnectivityOutcome, SkipReason, assess_response
from ...net.errors import FailureReason, RequestError
from ...plugins.models import SourceTrait
from ..base import Crawler, CrawlerProfile
from ..models import FetchOptions, FilmActor, MediaMetadata, SearchQuery
from ..parsing import fold_studio, is_same_number, parse_western_number

_PERFORMER_GENDER: dict[str, ActorGender] = {
    "FEMALE": ActorGender.FEMALE,
    "MALE": ActorGender.MALE,
}

if TYPE_CHECKING:
    from ...parsing.file_info import ContentType

type ContentKind = Literal["scene", "movie"]

_CONTENT_FIELDS = """
    id title code date duration director details
    studio { name }
    tags { name }
    performers { as performer { name gender } }
    images { url }
"""

_SCENE_SEARCH_QUERY = f"""
query Search($term: String!) {{
  searchScene(term: $term) {{{_CONTENT_FIELDS}
  }}
}}"""

_SCENE_FINGERPRINT_QUERY = f"""
query Find($fingerprints: [[FingerprintQueryInput!]!]!) {{
  findScenesBySceneFingerprints(fingerprints: $fingerprints) {{{_CONTENT_FIELDS}
  }}
}}"""

_SCENE_FIND_BY_ID_QUERY = f"""
query FindByID($id: ID!) {{
  findScene(id: $id) {{{_CONTENT_FIELDS}
  }}
}}"""

_MOVIE_API_URL = "https://api.theporndb.net/movies"

_TYPE_FILTER: dict[str, str] = {
    "censored": "JAV",
    "uncensored": "Scene",
    "western": "Scene",
    "fc2": "Scene",
    "amateur": "Scene",
    "hentai": "JAV",
}


class ThePornDBCrawler(Crawler):
    """Scenes use GraphQL; western movie lookup uses the Movies REST API."""

    @classmethod
    def profile(cls) -> CrawlerProfile:
        return CrawlerProfile(
            name=SiteName.THEPORNDB,
            base_url="https://theporndb.net/graphql",
            traits=frozenset({SourceTrait.USES_FILE_HASH}),
        )

    @override
    async def check_connectivity(self) -> ConnectivityOutcome:
        """真发一次 GraphQL 请求: 本源只有带 token 才会请求, 探测必须同样验证凭据与连通性.

        查一个不存在的 id: 应答便宜, 且能区分「token 被拒」与「站点不可达」. 地址经 ``_gql_url``
        取: ``?type=`` 是每次请求的过滤条件, 探测验证的是可达性与凭据, 不加该条件.
        """
        token = self.config.api_token if self.config else None
        if not token:
            return ConnectivityOutcome.skipped(SkipReason.MISSING_CREDENTIAL, "api_token")
        url = self._gql_url(None)
        try:
            resp = await self.client.web_client.request(
                "POST",
                url,
                json={"query": _SCENE_FIND_BY_ID_QUERY, "variables": {"id": "0"}},
                headers={"Authorization": f"Bearer {token}"},
                max_attempts=1,
            )
        except RequestError as exc:
            return ConnectivityOutcome.failed(exc.reason, url=url, http_status=exc.http_status)

        try:
            payload = resp.json()
        except Exception:
            payload = None
        if isinstance(payload, dict) and payload.get("errors") and not payload.get("data"):
            # HTTP 状态正常而在 GraphQL 层失败: 原因不写在状态码上. 上游的错误文本是英文原文, 截断后作为
            # 可行动信息报给用户 (不含 Authorization 头), 完整应答写入日志.
            errors = payload["errors"]
            self.logger.warning("theporndb graphql errors", errors=errors)
            message = ""
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                message = str(errors[0].get("message") or "")
            return ConnectivityOutcome.failed(FailureReason.API_ERROR, url=url, detail=message[:200] or None)
        return assess_response(url, resp)

    async def fetch(self, query: SearchQuery, options: FetchOptions | None = None) -> MediaMetadata | None:
        """Search scenes with GraphQL and movies with REST, fetching movie details by id."""
        token = self.config.api_token if self.config else None
        if not token:
            return None

        content = await self._search_content(query, token)
        if content is None:
            return None
        kind, item = content
        if kind == "scene":
            return _content_to_metadata(kind, item, query.number)
        movie_id = item.get("id")
        if not isinstance(movie_id, str) or not movie_id:
            return None
        data = await self.client.get_json(
            f"{_MOVIE_API_URL}/{quote(movie_id, safe='')}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        movie = _api_data(data)
        return _content_to_metadata(kind, movie, query.number) if isinstance(movie, dict) else None

    async def _search(self, query: SearchQuery, options: FetchOptions | None = None) -> str | None:
        """与 ``fetch`` 共用检索流程与命中判据."""
        token = self.config.api_token if self.config else None
        if not token:
            return None

        content = await self._search_content(query, token)
        return _content_url(*content, query.number) if content is not None else None

    async def _search_content(self, query: SearchQuery, token: str) -> tuple[ContentKind, dict[str, Any]] | None:
        """指纹优先; 欧美条目先匹配 scene, 再匹配 movie."""
        headers = {"Authorization": f"Bearer {token}"}
        gql_url = self._gql_url(query.content_type)

        if query.file_hash:
            data = await self.client.post_json(
                gql_url,
                json={
                    "query": _SCENE_FINGERPRINT_QUERY,
                    "variables": {
                        "fingerprints": [[{"hash": query.file_hash, "algorithm": "OSHASH"}]],
                    },
                },
                headers=headers,
            )
            results = _gql_field(data, "findScenesBySceneFingerprints")
            if (
                isinstance(results, list)
                and results
                and isinstance(results[0], list)
                and results[0]
                and isinstance(results[0][0], dict)
            ):
                return "scene", results[0][0]

        data = await self.client.post_json(
            gql_url,
            json={"query": _SCENE_SEARCH_QUERY, "variables": {"term": query.number}},
            headers=headers,
        )
        content = pick_content(_gql_field(data, "searchScene"), query.number)
        if content is not None:
            return "scene", content

        if query.content_type is not None and str(query.content_type) != "western":
            return None

        params = urlencode({"parse": query.number, "hash": "", "year": ""})
        data = await self.client.get_json(
            f"{_MOVIE_API_URL}?{params}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        content = pick_content(_api_data(data), query.number)
        return ("movie", content) if content is not None else None

    async def _scrape(self, url: str, options: FetchOptions | None = None) -> MediaMetadata | None:
        token = self.config.api_token if self.config else None
        if not token:
            return None

        number: str | None = None
        if url.startswith("gql://scene/"):
            kind: ContentKind = "scene"
            content_id = url.removeprefix("gql://scene/")
        elif url.startswith("api://movie/"):
            kind = "movie"
            parsed_url = urlsplit(url)
            content_id = unquote(parsed_url.path.removeprefix("/"))
            number = parse_qs(parsed_url.query).get("number", [None])[0]
        else:
            return None
        headers = {"Authorization": f"Bearer {token}"}

        if not content_id:
            return None
        if kind == "movie":
            data = await self.client.get_json(
                f"{_MOVIE_API_URL}/{quote(content_id, safe='')}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            content = _api_data(data)
            return _content_to_metadata(kind, content, number) if isinstance(content, dict) else None

        data = await self.client.post_json(
            self.base_url,
            json={"query": _SCENE_FIND_BY_ID_QUERY, "variables": {"id": content_id}},
            headers=headers,
        )

        content = _gql_field(data, "findScene")
        return _content_to_metadata(kind, content) if isinstance(content, dict) else None

    def _gql_url(self, content_type: ContentType | None) -> str:
        if content_type:
            gql_type = _TYPE_FILTER.get(str(content_type))
            if gql_type:
                return f"{self.base_url}?type={gql_type}"
        return self.base_url


def _content_to_metadata(
    kind: ContentKind,
    content: dict[str, Any],
    number: str | None = None,
) -> MediaMetadata:
    if kind == "movie":
        return _movie_to_metadata(content, number)

    scene_number = content.get("code") or content.get("title", "")
    studio = content.get("studio")
    studio_name = studio.get("name") if isinstance(studio, dict) else None

    actors: list[FilmActor] = []
    for appearance in content.get("performers", []) or []:
        performer = (appearance or {}).get("performer", {}) or {}
        name = performer.get("name") or appearance.get("as", "")
        if not name:
            continue
        gender = _PERFORMER_GENDER.get(str(performer.get("gender") or ""))
        actors.append(FilmActor(name=name, gender=gender or ActorGender.UNKNOWN))

    tags = [tag.get("name", "") for tag in (content.get("tags") or []) if tag.get("name")]
    images = content.get("images") or []
    thumb_url = images[0]["url"] if images else None

    return MediaMetadata(
        number=scene_number,
        title=content.get("title") or None,
        actors=actors,
        studio=studio_name,
        release=content.get("date") or None,
        runtime=_runtime_minutes(content.get("duration")),
        tags=tags,
        directors=[content["director"]] if content.get("director") else [],
        plot=content.get("details") or None,
        thumb_urls=[thumb_url] if thumb_url else [],
        external_id=content.get("id") or None,
        source_url=f"https://theporndb.net/{kind}s/{content['id']}" if content.get("id") else None,
    )


def _movie_to_metadata(content: dict[str, Any], number: str | None) -> MediaMetadata:
    site = content.get("site")
    studio_value = site.get("name") if isinstance(site, dict) else None
    studio = studio_value if isinstance(studio_value, str) else None
    raw_performers = content.get("performers")
    actors: list[FilmActor] = []
    if isinstance(raw_performers, list):
        for performer in raw_performers:
            if not isinstance(performer, dict):
                continue
            parent = performer.get("parent")
            if isinstance(parent, dict):
                performer = parent
            extras = performer.get("extras")
            extras = extras if isinstance(extras, dict) else {}
            name = performer.get("name")
            if not isinstance(name, str) or not name:
                continue
            gender_value = performer.get("gender") or extras.get("gender")
            gender = _PERFORMER_GENDER.get(str(gender_value or "").upper())
            actors.append(FilmActor(name=name, gender=gender or ActorGender.UNKNOWN))

    raw_tags = content.get("tags")
    tags = (
        [tag["name"] for tag in raw_tags if isinstance(tag, dict) and isinstance(tag.get("name"), str) and tag["name"]]
        if isinstance(raw_tags, list)
        else []
    )
    raw_directors = content.get("directors")
    directors = (
        [
            director["name"]
            for director in raw_directors
            if isinstance(director, dict) and isinstance(director.get("name"), str) and director["name"]
        ]
        if isinstance(raw_directors, list)
        else []
    )
    poster_url = _image_url(content.get("posters")) or _image_url(content.get("poster"))
    trailer = content.get("trailer")
    background_url = _image_url(content.get("background"))
    background_back_url = _image_url(content.get("background_back"))
    rating = content.get("rating")
    content_id = content.get("id")
    slug = content.get("slug")
    title = content.get("title")
    code = content.get("code")
    movie_number = number or (code if isinstance(code, str) else None) or (title if isinstance(title, str) else "")
    release = content.get("date")
    description = content.get("description")

    return MediaMetadata(
        number=movie_number,
        title=title if isinstance(title, str) and title else None,
        actors=actors,
        studio=studio,
        release=release if isinstance(release, str) else None,
        runtime=_runtime_minutes(content.get("duration")),
        tags=tags,
        directors=directors,
        plot=description if isinstance(description, str) and description else None,
        poster_urls=[poster_url] if poster_url else [],
        thumb_urls=[background_url] if isinstance(background_url, str) and background_url else [],
        trailer_urls=[trailer] if isinstance(trailer, str) and trailer else [],
        score=float(rating)
        if isinstance(rating, int | float) and not isinstance(rating, bool) and rating > 0
        else None,
        external_id=content_id if isinstance(content_id, str) else None,
        source_url=f"https://theporndb.net/movies/{slug}" if isinstance(slug, str) and slug else None,
        extrafanart=[background_back_url] if isinstance(background_back_url, str) and background_back_url else [],
    )


def _image_url(value: object) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        for size in ("large", "full", "medium", "small"):
            url = value.get(size)
            if isinstance(url, str) and url:
                return url
    return None


def pick_content(results: object, number: str) -> dict[str, Any] | None:
    """检索结果 → 命中的条目; 确认不了返回 None, 不回退首条.

    ``code`` 与入参按同一番号判定, 欧美日期号的两种年份写法等价, 命中取应答里的首条.
    欧美条目的 ``code`` 是 ``studio:title-slug``, 与文件名番号不同构, 这类日期号按
    片商 + 发布日期确认, 只认唯一命中.
    """
    contents = [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []
    for content in contents:
        code = content.get("code")
        if isinstance(code, str) and code and is_same_number(code, number):
            return content

    western = parse_western_number(number)
    if western is None:
        return None
    hits = [
        content
        for content in contents
        if _content_date(content) == western.date and fold_studio(_content_studio(content)) == western.studio
    ]
    return hits[0] if len(hits) == 1 else None


def _content_studio(content: dict[str, Any]) -> str:
    studio = content.get("studio")
    if not isinstance(studio, dict):
        studio = content.get("site")
    name = studio.get("name") if isinstance(studio, dict) else None
    return name if isinstance(name, str) else ""


def _content_date(content: dict[str, Any]) -> str:
    date = content.get("date")
    return date if isinstance(date, str) else ""


def _runtime_minutes(duration: object) -> int | None:
    """秒 → 分钟; 缺省与 0 视为没有时长."""
    if isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
        return None
    return duration // 60


def _content_url(kind: ContentKind, content: dict[str, Any], number: str | None = None) -> str | None:
    content_id = content.get("id")
    if not isinstance(content_id, str) or not content_id:
        return None
    if kind == "scene":
        return f"gql://scene/{content_id}"
    return f"api://movie/{quote(content_id, safe='')}?{urlencode({'number': number or ''})}"


def _gql_field(payload: object, key: str) -> object:
    """取 GraphQL 应答的 ``data.<key>``; 结构不符返回 None."""
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    return data.get(key) if isinstance(data, dict) else None


def _api_data(payload: object) -> object:
    return payload.get("data") if isinstance(payload, dict) else None
