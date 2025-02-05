from typing import Union

from fastapi import FastAPI

import audio_splicer
from media import MediaLoader

media_loader = MediaLoader()
audio_splicer.insert_add(
    media_loader.music_track,
    media_loader.random_ad(),
    media_loader.target_bytes_size(),
)

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}