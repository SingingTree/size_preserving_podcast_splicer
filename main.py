import logging
import sys
import pathlib

from fastapi import FastAPI
from fastapi.responses import FileResponse

from starlette.background import BackgroundTask

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

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/pretend_podcast_that_is_actually_music")
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
