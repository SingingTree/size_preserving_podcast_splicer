"""
FastAPI application that serves a pretend podcast feed with dynamic ad insertion.

This module provides endpoints for:
- Serving a static HTML index page
- Generating an RSS feed for the podcast
- Streaming audio content with ad insertion and byte range support

The application uses MediaLoader for handling audio files and AudioSplicer for
inserting ads into the audio stream. All responses are configured to avoid
caching to ensure different ad insertions on refresh.

Endpoints:
    GET / - Serves the main HTML page
    GET /rss - Generates RSS feed for the podcast
    GET /pretend_podcast_that_is_actually_music - Serves music with dynamic ad
        insertion and byte range support.
"""

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response

from feedgen.feed import FeedGenerator  # type: ignore

from app.size_preserving_podcast_splicer import media_loader, audio_splicer

root = logging.getLogger()
root.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
root.addHandler(handler)

loader = media_loader.MediaLoader()
splicer = audio_splicer.AudioSplicer()

BASE_DIR = Path(__file__).parent.parent.resolve()
STATIC_DIR = BASE_DIR / "static"

EPISODE_PATH = "/pretend_podcast_that_is_actually_music"
RSS_PATH = "/rss"

app = FastAPI()


@app.get("/")
async def read_root():
    """Serve the main HTML interface for the app.

    Returns a static HTML page that shows a mock podcast audio in an <audio>
    element along with links to the other endpoints available. The response
    includes cache-control headers to ensure fresh content on each load.

    Returns:
        FileResponse: HTML content with no-cache headers:
            - Cache-Control: no-cache, no-store, must-revalidate
            - Pragma: no-cache
            - Expires: 0
    """
    return FileResponse(
        STATIC_DIR / "index.html",
        # Avoid caching so it's easier to get different ad inserts on refresh.
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get(RSS_PATH)
async def rss(request: Request):
    """Generate a dynamic RSS feed for the pretend podcast.

     Creates an RSS feed containing metadata about the podcast episode,
    including title, description, and audio enclosure information.
    The feed is generated dynamically based on the current audio content.

    Args:
        request (Request): The incoming HTTP request, used to generate
            absolute URLs for the feed

    Returns:
        Response: RSS XML content with media type 'application/rss+xml'
            containing:
            - Podcast title and description
            - Episode metadata
            - Audio enclosure information with correct file size
    """
    base_url = str(request.base_url).rstrip("/")

    def make_url(path: str) -> str:
        # Ensures proper URL joining
        return urljoin(base_url, path.lstrip("/"))

    music_probe_data = loader.music_track.probe
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
    fe.enclosure(make_url(EPISODE_PATH), loader.target_bytes_size(), "audio/mpeg")

    # Generate and return the RSS feed.
    return Response(content=fg.rss_str(), media_type="application/rss+xml")


@app.get(EPISODE_PATH)
async def pretend_podcast_that_is_actually_music(request: Request):
    """Stream audio content with dynamically inserted advertisements.

    Serves an audio file with dynamically inserted advertisements, supporting
    HTTP range requests for partial content delivery. The audio is processed
    to maintain consistent file size while incorporating ads.

    Args:
        request (Request): The incoming HTTP request, containing potential
            'Range' header for partial content requests

    Returns:
        Response: Audio content with appropriate headers:
            - For partial content: status 206 with Content-Range header
            - For full content: status 200
            - Always includes:
                - Content-Disposition for filename
                - Content-Length
                - Accept-Ranges: bytes
                - Cache-Control headers preventing caching

    Technical Details:
        - Supports byte range requests for partial content delivery
        - Dynamically inserts ads while maintaining target file size
        - Uses no-cache headers to ensure fresh ad insertion on each request
        - Returns audio/mpeg content type
    """
    audio_bytes = splicer.insert_ad_and_pad(
        loader.music_track,
        loader.random_ad(),
        loader.target_bytes_size(),
    )

    audio_size = len(audio_bytes)
    music_file_name = os.path.basename(loader.music_track.probe["format"]["filename"])

    # Parse range header if present
    range_header = request.headers.get("range")

    if range_header:
        start_byte = 0
        end_byte = audio_size - 1

        if range_header.startswith("bytes="):
            range_data = range_header.split("=")[1]
            ranges = range_data.split("-")

            if ranges[0]:
                start_byte = int(ranges[0])
            if ranges[1]:
                end_byte = int(ranges[1])

        # Get the requested byte range
        content = audio_bytes[start_byte : end_byte + 1]
        content_length = len(content)

        headers = {
            "Content-Disposition": f'attachment; filename="{music_file_name}"',
            "Content-Length": str(content_length),
            "Content-Range": f"bytes {start_byte}-{end_byte}/{audio_size}",
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }

        return Response(
            content=content,
            status_code=206,  # Partial Content
            media_type="audio/mpeg",
            headers=headers,
        )

    # If no range header, return full content as before
    headers = {
        "Content-Disposition": f'attachment; filename="{music_file_name}"',
        "Content-Length": str(audio_size),
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    return Response(content=audio_bytes, media_type="audio/mpeg", headers=headers)
