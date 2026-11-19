"""Pictures of an anime for the interface: frames of its episodes and of its trailer.

The catalog has only the poster of an anime. A poster does not show how the anime looks on the
screen. AniList has more pictures: one picture for each episode that a streaming site has, the
trailer, and a banner. The build does not get them, because only the Discover deck uses them,
for a few shows at a time. Thus the server asks AniList when the deck shows its cards, and it
keeps each answer in a file.
"""
import json
import re
import threading
import time

from . import anilist_pull

QUERY = ("query ($ids: [Int]) { Page(perPage: 50) { media(id_in: $ids, type: ANIME) { "
         "id status bannerImage trailer { id site thumbnail } streamingEpisodes { title thumbnail } } } }")
# The largest number of anime in one request to AniList
BATCH = 50
# The number of frames from the episodes, and from the trailer
EPISODE_FRAMES = 3
TRAILER_FRAMES = 3
# The file of an anime is good for this number of days
MAX_AGE_DAYS = 30
# An anime that is not finished gets episodes and a trailer with time. An anime without pictures
# can get them later. The file of such an anime is good for this number of days.
SHORT_MAX_AGE_DAYS = 7
# Seconds to wait for the answer of AniList. The deck works without the pictures, thus the time is short.
TIMEOUT = 15
EPISODE_NUMBER = re.compile(r"^\s*Episode\s+(\d+(?:\.\d+)?)", re.IGNORECASE)
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
DAILYMOTION_ID = re.compile(r"^[A-Za-z0-9]{4,20}$")
# Only one thread asks AniList at a time. A second request for the same anime then finds the file.
_LOCK = threading.Lock()


def _address(text) -> str | None:
    """Return the text if it is a safe address of a picture. The interface puts the address in the page."""
    if isinstance(text, str) and text.startswith("https://") and not any(c in text for c in "\"'<> \\\n\r\t"):
        return text
    return None


def pictures_from_media(m: dict) -> dict:
    """Return the pictures of one anime from the answer of AniList.

    `frames` has the frames in the order in which the interface shows them: the first episodes,
    then the trailer. Each frame has a small picture, a large picture and a label. `trailer` is
    the address of the trailer, and `banner` is the address of the banner. A value is None or
    empty if AniList does not have it.

    The frames of the episodes come from the first episodes: they show the look of the anime,
    and they do not show the end of the story. YouTube keeps three frames of each video: at one
    quarter, at one half and at three quarters of its length.
    """
    frames: list[dict] = []
    episodes = []
    for position, episode in enumerate(m.get("streamingEpisodes") or []):
        picture = _address((episode or {}).get("thumbnail"))
        if picture is None:
            continue
        title = str(episode.get("title") or "")
        found = EPISODE_NUMBER.match(title)
        # An entry without a number, for example a teaser, comes after the episodes
        episodes.append((found is None, float(found.group(1)) if found else 0.0, position, picture,
                         f"Episode {found.group(1)}" if found else (title[:40] or "Episode")))
    seen: set[str] = set()
    for _, _, _, picture, label in sorted(episodes):
        if picture in seen:
            continue
        seen.add(picture)
        frames.append({"small": picture, "large": picture, "label": label})
        if len(frames) >= EPISODE_FRAMES:
            break

    trailer = m.get("trailer") or {}
    site, video = trailer.get("site"), str(trailer.get("id") or "")
    address = None
    if site == "youtube" and YOUTUBE_ID.match(video):
        address = f"https://www.youtube.com/watch?v={video}"
        for n in range(1, TRAILER_FRAMES + 1):
            # The large picture is not there for an old video. The interface then uses the small picture.
            frames.append({"small": f"https://i.ytimg.com/vi/{video}/mq{n}.jpg",
                           "large": f"https://i.ytimg.com/vi/{video}/maxres{n}.jpg", "label": "Trailer"})
    elif site == "dailymotion" and DAILYMOTION_ID.match(video):
        address = f"https://www.dailymotion.com/video/{video}"
        picture = _address(trailer.get("thumbnail"))
        if picture:
            frames.append({"small": picture, "large": picture, "label": "Trailer"})
    return {"frames": frames, "trailer": address, "banner": _address(m.get("bannerImage"))}


def _file(anilist_id: int):
    return anilist_pull.CACHE_DIR / "frames" / f"{int(anilist_id)}.json"


def _read(anilist_id: int, any_age: bool = False) -> dict | None:
    """Return the answer of AniList for one anime from its file. Return None if there is no good file."""
    path = _file(anilist_id)
    try:
        media = json.loads(path.read_text(encoding="utf-8"))
        age_days = (time.time() - path.stat().st_mtime) / 86400.0
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(media, dict):
        return None
    if any_age:
        return media
    short = (media.get("absent") or media.get("status") in anilist_pull.UNFINISHED
             or not pictures_from_media(media)["frames"])
    return media if age_days <= (SHORT_MAX_AGE_DAYS if short else MAX_AGE_DAYS) else None


def _fetch(ids: list[int]) -> list[dict]:
    data = anilist_pull._post(QUERY, {"ids": ids}, TIMEOUT)
    page = (data.get("data") or {}).get("Page")
    if not page:
        raise RuntimeError(f"AniList returned no data for ids {ids[:3]}: {str(data)[:200]}")
    return page["media"] or []


def get_pictures(anilist_ids) -> dict[int, dict]:
    """Return the pictures of the anime with these AniList ids, by the id.

    The function asks AniList only for the anime that have no good file. If AniList does not
    answer, an anime with an old file gets its old pictures, and an anime without a file is not
    in the result. The function does not raise an error for this: the caller works without the
    pictures.
    """
    wanted = sorted({int(i) for i in anilist_ids})
    out: dict[int, dict] = {}
    todo = []
    for i in wanted:
        media = _read(i)
        if media is None:
            todo.append(i)
        else:
            out[i] = pictures_from_media(media)
    if not todo:
        return out
    with _LOCK:
        for start in range(0, len(todo), BATCH):
            batch = []
            for i in todo[start:start + BATCH]:
                # A different thread wrote the file in the time that this thread waited
                media = _read(i)
                if media is None:
                    batch.append(i)
                else:
                    out[i] = pictures_from_media(media)
            if not batch:
                continue
            try:
                got = {int(m["id"]): m for m in _fetch(batch)}
            except Exception as err:
                print(f"WARNING no pictures from AniList for {len(batch)} anime ({err!r})")
                for i in batch:
                    media = _read(i, any_age=True)
                    if media is not None:
                        out[i] = pictures_from_media(media)
                continue
            _file(batch[0]).parent.mkdir(parents=True, exist_ok=True)
            for i in batch:
                # AniList does not return an adult anime or a removed entry. The file keeps this
                # result, so that the server does not ask again each time.
                media = got.get(i) or {"id": i, "absent": True}
                _file(i).write_text(json.dumps(media), encoding="utf-8")
                out[i] = pictures_from_media(media)
    return out
