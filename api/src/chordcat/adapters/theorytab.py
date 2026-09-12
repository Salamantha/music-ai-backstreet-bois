"""Search Hooktheory's TheoryTab database by roman-numeral chord string.

This is a *second* source, used alongside the Trends API, because the Trends
`trends/songs` index is a stale snapshot: Arctic Monkeys' "505" is in
TheoryTab as D Dorian `i ii i ii`, the correct Trends token for that is `2,3`,
and an exhaustive scan of `2,3` (all 17 pages, 338 songs) does not contain it.
Other D-dorian i-ii songs *are* there, so the mapping is right and the index is
simply missing entries.

Three things to be clear about:

* **This is not an API.** It parses the server-rendered advanced-search page.
  There is no JSON endpoint behind it -- the network trace shows the results
  arrive in the HTML document itself. Markup changes will break it, so every
  field is optional and a parse failure degrades to "no results" rather than
  raising into a user's analysis.
* **It is accessed politely.** One request at a time, well under a request per
  second, aggressively cached, with a descriptive User-Agent. `robots.txt`
  allows the path (`User-agent: *` / `Allow: /`) and its content signal is
  `use=reference`, which is what this is: looking songs up to show a person.
* **It queries in roman numerals, not `cp` tokens.** That is a better fit for a
  chord-voicing device: `ignore_modifiers` makes `i ii` match a song whose
  chords are really i11 and ii9, which is exactly what the ChordCat sends.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from typing import Protocol, Sequence

import httpx

log = logging.getLogger(__name__)

SEARCH_URL = "https://www.hooktheory.com/theorytab/advanced-search"
VIEW_BASE = "https://www.hooktheory.com"
#: Result thumbnails are YouTube stills, so the video id comes free.
_YOUTUBE_THUMB = re.compile(r"img\.youtube\.com/vi/([A-Za-z0-9_-]{6,})/")
USER_AGENT = (
    "ChordCat-Connect/0.1 (musician matching; contact via project repository)"
)
#: Deliberately unhurried. This is someone's website, not an API.
MIN_REQUEST_INTERVAL_S = 1.2
RESULTS_PER_PAGE = 50
#: A two-chord query legitimately matches hundreds of songs, and the one a
#: player is thinking of can be well down the list -- Arctic Monkeys' "505" is
#: on page 7 of `i ii`. Results are cached, so the paging cost is paid once per
#: progression, not once per analysis.
DEFAULT_MAX_PAGES = 8
#: Part of the cache key. Bump when the parsed shape changes, so entries written
#: by an older parser are ignored rather than deserialised into missing fields.
PARSE_VERSION = 2


@dataclass(frozen=True, slots=True)
class TheoryTabHit:
    song: str
    artist: str
    section: str
    url: str
    key_tonic: str = ""
    scale: str = ""
    tempo: int | None = None
    #: Roman numerals as Hooktheory analyses them.
    chords: tuple[str, ...] = ()
    #: The leading chords the search highlighted as the match.
    matched: tuple[str, ...] = ()
    genres: tuple[str, ...] = ()
    #: Taken from the result's thumbnail, which is a YouTube still.
    youtube_id: str = ""

    @property
    def youtube_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.youtube_id}" if self.youtube_id else ""

    @property
    def key_name(self) -> str:
        return f"{self.key_tonic} {self.scale}".strip()


class TheoryTabClient(Protocol):
    async def search(
        self, chord_string: str, *, page: int = 1, ignore_modifiers: bool = True
    ) -> list[TheoryTabHit]: ...

    async def search_all(
        self,
        chord_string: str,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
        ignore_modifiers: bool = True,
    ) -> list[TheoryTabHit]: ...


class _ResultParser(HTMLParser):
    """Pull the results table out of the advanced-search page.

    Written against stable `asr-*` class names. Every field is optional: a row
    that does not parse is skipped rather than aborting the page.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hits: list[TheoryTabHit] = []
        self._row: dict[str, object] | None = None
        self._cell: str | None = None
        self._buffer: list[str] = []
        self._in_bold = False
        self._scale_parts: list[str] = []
        self._depth_at_cell = 0

    # -- helpers -----------------------------------------------------------
    def _flush(self) -> str:
        text = unescape("".join(self._buffer)).strip()
        self._buffer = []
        return re.sub(r"\s+", " ", text)

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {k: (v or "") for k, v in attrs_list}
        classes = attrs.get("class", "").split()

        if tag == "tr":
            self._row = {"chords": [], "matched": [], "scale_parts": []}
            return
        if self._row is None:
            return

        if tag == "td":
            for name in ("section", "scale", "tempo", "genre"):
                if f"asr-{name}" in classes:
                    self._cell = name
                    self._buffer = []
                    return
            self._cell = None
            self._buffer = []
        elif tag == "div":
            if "asr-song-title" in classes:
                self._cell, self._buffer = "song", []
            elif "asr-song-artist" in classes:
                self._cell, self._buffer = "artist", []
            elif "asr-chords-text" in classes:
                self._cell, self._buffer = "chords", []
            elif self._cell == "scale":
                self._buffer = []
        elif tag == "img":
            found = _YOUTUBE_THUMB.search(attrs.get("src", ""))
            if found:
                self._row.setdefault("youtube_id", found.group(1))
        elif tag == "a" and self._cell == "song":
            href = attrs.get("href", "")
            if href.startswith("/"):
                self._row["url"] = VIEW_BASE + href
        elif tag == "b" and self._cell == "chords":
            self._in_bold = True
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        if self._row is None:
            return

        if tag == "b" and self._cell == "chords":
            token = self._flush()
            if token:
                self._row["matched"].append(token)  # type: ignore[union-attr]
                self._row["chords"].append(token)  # type: ignore[union-attr]
            self._in_bold = False
            return

        if tag == "div" and self._cell == "scale":
            part = self._flush()
            if part:
                self._row["scale_parts"].append(part)  # type: ignore[union-attr]
            return

        if tag == "div" and self._cell == "chords":
            self._row["chords"].extend(self._flush().split())  # type: ignore[union-attr]
            self._cell = None
            return

        if tag in ("td", "div") and self._cell in ("song", "artist", "section", "tempo", "genre"):
            value = self._flush()
            if value:
                self._row.setdefault(self._cell, value)
            self._cell = None
            return

        if tag == "tr":
            self._finish_row()

    def handle_data(self, data: str) -> None:
        if self._row is not None and self._cell is not None:
            self._buffer.append(data)

    def _finish_row(self) -> None:
        row, self._row, self._cell = self._row, None, None
        if not row or not row.get("song") or not row.get("url"):
            return
        scale_parts = row.get("scale_parts") or []
        tempo_raw = str(row.get("tempo", "")).strip()
        artist = str(row.get("artist", ""))
        self.hits.append(
            TheoryTabHit(
                song=str(row["song"]),
                artist=re.sub(r"^by\s+", "", artist, flags=re.I),
                section=str(row.get("section", "")),
                url=str(row["url"]),
                key_tonic=scale_parts[0] if scale_parts else "",
                scale=scale_parts[1] if len(scale_parts) > 1 else "",
                tempo=int(tempo_raw) if tempo_raw.isdigit() else None,
                chords=tuple(row.get("chords") or ()),
                matched=tuple(row.get("matched") or ()),
                genres=tuple(
                    g.strip() for g in str(row.get("genre", "")).split(",") if g.strip()
                ),
                youtube_id=str(row.get("youtube_id", "")),
            )
        )


def parse_results(html_text: str) -> list[TheoryTabHit]:
    parser = _ResultParser()
    try:
        parser.feed(html_text)
    except Exception as exc:  # noqa: BLE001 - a markup change must not break analysis
        log.warning("TheoryTab result parsing failed: %s", exc)
        return []
    return parser.hits


@dataclass(slots=True)
class HttpTheoryTabClient:
    """Live client. Serialised and rate limited by construction."""

    cache: object | None = None
    min_interval_s: float = MIN_REQUEST_INTERVAL_S
    timeout_s: float = 20.0
    _client: httpx.AsyncClient | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _last_request: float = 0.0

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_s),
                headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
                follow_redirects=True,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def search(
        self, chord_string: str, *, page: int = 1, ignore_modifiers: bool = True
    ) -> list[TheoryTabHit]:
        chord_string = " ".join(chord_string.split())
        if not chord_string:
            return []

        key = f"tt|v{PARSE_VERSION}|{chord_string}|{page}|{int(ignore_modifiers)}"
        if self.cache is not None:
            cached = self.cache.get_theorytab(key)  # type: ignore[attr-defined]
            if cached is not None:
                return [
                    TheoryTabHit(
                        **{
                            **row,
                            "chords": tuple(row.get("chords") or ()),
                            "matched": tuple(row.get("matched") or ()),
                            "genres": tuple(row.get("genres") or ()),
                        }
                    )
                    for row in cached
                ]

        params = {
            "chordString": chord_string,
            "keySelect": "any",
            "scaleSelect": "any",
            "startOfSection": "0",
            "ignoreModifiers": "1" if ignore_modifiers else "0",
            "page": str(page),
        }

        async with self._lock:
            gap = self.min_interval_s - (time.monotonic() - self._last_request)
            if gap > 0:
                await asyncio.sleep(gap)
            try:
                client = await self._http()
                resp = await client.get(SEARCH_URL, params=params)
            finally:
                self._last_request = time.monotonic()

        if resp.status_code != 200:
            log.warning("TheoryTab search %s -> HTTP %s", chord_string, resp.status_code)
            return []

        hits = parse_results(resp.text)
        if self.cache is not None:
            self.cache.put_theorytab(  # type: ignore[attr-defined]
                key, [_as_dict(h) for h in hits]
            )
        return hits

    async def search_all(
        self,
        chord_string: str,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
        ignore_modifiers: bool = True,
    ) -> list[TheoryTabHit]:
        return await _paged(self, chord_string, max_pages, ignore_modifiers)


async def _paged(
    client, chord_string: str, max_pages: int, ignore_modifiers: bool
) -> list[TheoryTabHit]:
    seen: set[tuple[str, str, str]] = set()
    out: list[TheoryTabHit] = []
    for page in range(1, max_pages + 1):
        hits = await client.search(
            chord_string, page=page, ignore_modifiers=ignore_modifiers
        )
        if not hits:
            break
        for hit in hits:
            key = (hit.artist, hit.song, hit.section)
            if key not in seen:
                seen.add(key)
                out.append(hit)
        if len(hits) < RESULTS_PER_PAGE:
            break
    return out


def _as_dict(hit: TheoryTabHit) -> dict:
    return {
        "song": hit.song, "artist": hit.artist, "section": hit.section,
        "url": hit.url, "key_tonic": hit.key_tonic, "scale": hit.scale,
        "tempo": hit.tempo, "chords": list(hit.chords), "matched": list(hit.matched),
        "genres": list(hit.genres), "youtube_id": hit.youtube_id,
    }


@dataclass(slots=True)
class FakeTheoryTabClient:
    """Fixture-backed client, so tests never touch the network."""

    fixtures: dict[str, list[TheoryTabHit]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    async def search(
        self, chord_string: str, *, page: int = 1, ignore_modifiers: bool = True
    ) -> list[TheoryTabHit]:
        self.calls.append(chord_string)
        return self.fixtures.get(chord_string, []) if page == 1 else []

    async def search_all(
        self,
        chord_string: str,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
        ignore_modifiers: bool = True,
    ) -> list[TheoryTabHit]:
        return await _paged(self, chord_string, max_pages, ignore_modifiers)


#: Everything after the numeral that `ignoreModifiers` is meant to disregard:
#: sevenths, sixths, suspensions and added tones. Chord *quality* is carried by
#: the numeral's case and by the degree symbol, so neither is stripped.
_MODIFIER = re.compile(
    r"(maj7|7sus4|7sus2|sus42|sus4|sus2|add9|add11|add13|7|6|9|11|13)+$"
)
_ROMAN = re.compile(r"^([b#]*)([ivxIVX]+)(o|0|\u00f8|\+)?")


def strip_modifiers(roman: str) -> str:
    """Reduce a roman numeral to the triad `ignoreModifiers` will match.

    The ChordCat voices nearly everything as an extended chord, so its
    progressions come out as `ii7 iii7` where Hooktheory analyses the same
    music as `ii iii`. Sending the sevenths through defeats the search: the
    `ignoreModifiers` flag relaxes the *database* side of the comparison, not
    the query, so the query has to be the plain triad.
    """
    match = _ROMAN.match(roman)
    if not match:
        return _MODIFIER.sub("", roman)
    accidental, numeral, quality = match.groups()
    return f"{accidental}{numeral}{quality or ''}"


def romans_to_chord_string(
    romans: Sequence[str], *, ignore_modifiers: bool = True
) -> str:
    """Render our roman numerals the way the search box expects them.

    Hooktheory writes degree symbols as `o` and half-diminished as `ø`, and uses
    no parentheses, so the display strings this project generates need a light
    normalisation before they go into a query.
    """
    out: list[str] = []
    for r in romans:
        token = r.strip()
        if not token or token.startswith("["):
            continue
        token = token.replace("\u00b0", "o").replace("\u266d", "b").replace("\u266f", "#")
        if ignore_modifiers:
            token = strip_modifiers(token)
        if token:
            out.append(token)
    return " ".join(out)
