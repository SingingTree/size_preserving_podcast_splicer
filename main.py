import logging
import sys
import pathlib
from datetime import datetime, timezone
from urllib.parse import urljoin

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response

from feedgen.feed import FeedGenerator

from starlette.background import BackgroundTask
from starlette.staticfiles import StaticFiles

import audio_splicer
import media_loader

root = logging.getLogger()
root.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
root.addHandler(handler)

media_loader = media_loader.MediaLoader()

EPISODE_PATH = "/pretend_podcast_that_is_actually_music"
RSS_PATH = "/rss"
app = FastAPI()

# Mount static files for general static content if needed
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_root():
    return FileResponse(
        "static/index.html",
        # Avoid caching so it's easier to get different ad inserts on refresh.
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@app.get(RSS_PATH)
async def rss(request: Request):
    base_url = str(request.base_url).rstrip("/")

    def make_url(path: str) -> str:
        # Ensures proper URL joining
        return urljoin(base_url, path.lstrip("/"))


    music_probe_data = media_loader.music_track.probe
    fg = FeedGenerator()

    # Generate the top level podcast.
    fg.title("My pretend podcast!")
    fg.description("A pretend podcast feed!")
    fg.link(href=make_url(RSS_PATH), rel="self")
    fg.language("en")

    # Add a single episode
    fe = fg.add_entry()
    fe.id(make_url(EPISODE_PATH))
    fe.title(music_probe_data["format"]["tags"]["title"])
    fe.description(music_probe_data["format"]["tags"]["comment"])
    fe.published(datetime.now(tz=timezone.utc))
    fe.enclosure(make_url(EPISODE_PATH), media_loader.target_bytes_size(), "audio/mpeg")

    # Generate and return the RSS feed.
    return Response(
        content=fg.rss_str(),
        media_type="application/rss+xml"
    )

@app.get(EPISODE_PATH)
async def pretend_podcast_that_is_actually_music():
    audio_path_string = audio_splicer.insert_ad_and_pad(
        media_loader.music_track,
        media_loader.random_ad(),
        media_loader.target_bytes_size(),
    )
    audio_path = pathlib.Path(audio_path_string)
    return FileResponse(
        path=audio_path,
        filename="your_file.pdf",
        background=BackgroundTask(lambda: audio_path.unlink(missing_ok=True)),
    )
