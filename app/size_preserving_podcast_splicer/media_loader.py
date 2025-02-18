"""Media loading utilities for audio streaming with ad insertion.

This module provides classes for loading and managing audio streams and
advertisements for a podcast system. It handles file path management,
stream probing, and size calculations for audio files using ffmpeg.

Classes:
    StreamAndProbe: Wrapper for ffmpeg streams with metadata from ffprobe
    MediaLoader: Loads the music and ads that the app uses
"""

import random
from pathlib import Path

import ffmpeg  # type: ignore

BASE_DIR = Path(__file__).parent.parent.parent.resolve()
MEDIA_DIR = BASE_DIR / "media"
ADS_DIR = MEDIA_DIR / "ads"
MUSIC_DIR = MEDIA_DIR / "music"


class StreamAndProbe:
    """Wrapper class for ffmpeg audio streams with probe metadata.

    Combines an ffmpeg input stream with its probe data for easy access
    to stream properties. Validates that the first stream is audio.

    Args:
        file_path (str): Path to the audio file

    Raises:
        AssertionError: If the first stream is not audio type

    Example:
        ```python
        stream = StreamAndProbe("/path/to/audio.mp3")
        duration = stream.duration()
        ```
    """

    def __init__(self, file_path: str) -> None:
        self.stream = ffmpeg.input(file_path)
        self.probe = ffmpeg.probe(file_path)
        # We expect the first stream in each file to be audio.
        assert self.probe["streams"][0]["codec_type"] == "audio"

    def duration(self) -> float:
        """Get the duration of the audio stream.

        Returns:
            float: Duration in seconds from the first audio stream's metadata
        """
        return float(self.probe["streams"][0]["duration"])

    def size(self) -> int:
        """Get the file size of the audio file.

        Returns:
            int: Size in bytes from the format metadata
        """
        return int(self.probe["format"]["size"])


class MediaLoader:
    """Manages access to music tracks and advertisement audio files.

    Loads and provides access to a music track and a collection of
    advertisements from predefined directories. Handles random ad selection
    and calculates target byte sizes for combined audio content.

    The loader expects:
        - Advertisements in BASE_DIR/media/ads/
        - Music in BASE_DIR/media/music/

    On initialization, loads all advertisements from the ads directory
    and a specific Bach music track.
    """

    def __init__(self) -> None:
        self.ads = [StreamAndProbe(str(path)) for path in ADS_DIR.glob("*")]
        self.music_track = StreamAndProbe(
            str(
                MUSIC_DIR
                / "Kimiko Ishizaka - J.S. Bach- -Open- Goldberg Variations, BWV 988 (Piano) - 15 Variatio 14 a 2 Clav.mp3"
            )
        )

    def random_ad(self) -> StreamAndProbe:
        """Select a random advertisement from the loaded collection.

        Returns:
            StreamAndProbe: Randomly selected advertisement stream
        """
        index = random.randint(0, len(self.ads) - 1)
        return self.ads[index]

    def music(self) -> StreamAndProbe:
        """Get the main music track.

        Returns:
            StreamAndProbe: The loaded music track stream
        """
        return self.music_track

    def target_bytes_size(self) -> int:
        """Calculate target size for combined music and ad content.

        Determines the optimal file size that can accommodate both the
        music track and an advertisement. Returns the smaller of:
            - Music size + largest ad size
            - Music size + 10% buffer

        In practice, this overestimates the size we need, but it is suitable for this toy project.

        Returns:
            int: Target size in bytes for the combined audio

        Note:
            This calculation ensures the final file size will be consistent
            regardless of which advertisement is inserted.
        """
        largest_ad_bytes_count = 0
        for ad in self.ads:
            if ad.size() > largest_ad_bytes_count:
                largest_ad_bytes_count = ad.size()

        # Return which ever is smaller:
        # - Num bytes in music + 10% extra buffer (for ads).
        # - Num bytes in music + num bytes in the largest ad.
        music_and_largest_ad_bytes_count = (
            self.music_track.size() + largest_ad_bytes_count
        )
        music_and_ten_percent_more_bytes_count = int(self.music_track.size() * 1.1)
        if music_and_largest_ad_bytes_count <= music_and_ten_percent_more_bytes_count:
            return music_and_largest_ad_bytes_count
        return music_and_ten_percent_more_bytes_count
