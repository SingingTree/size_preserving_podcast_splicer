import os
import random

import ffmpeg  # type: ignore


class StreamAndProbe:
    def __init__(self, file_path: str) -> None:
        self.stream = ffmpeg.input(file_path)
        self.probe = ffmpeg.probe(file_path)
        # We expect the first stream in each file to be audio.
        assert(self.probe["streams"][0]["codec_type"] == "audio")

    def duration(self) -> float:
        """Returns the duration of the stream in seconds."""
        return float(self.probe["streams"][0]["duration"])

    def size(self) -> int:
        """Returns the size of the file in bytes."""
        return int(self.probe["format"]["size"])


class MediaLoader:
    def __init__(self) -> None:
        ad_dir = "./media/ads"
        ad_files = os.listdir(ad_dir)
        ad_paths = [ad_dir + "/" + ad_file for ad_file in ad_files]
        self.ads = [StreamAndProbe(ad_path) for ad_path in ad_paths]
        self.music_track = StreamAndProbe("./media/music/Kimiko Ishizaka - J.S. Bach- -Open- Goldberg Variations, BWV 988 (Piano) - 15 Variatio 14 a 2 Clav.mp3")

    def random_ad(self) -> StreamAndProbe:
        index = random.randint(0, len(self.ads) - 1)
        return self.ads[0]

    def music(self) -> StreamAndProbe:
        return self.music_track

    def target_bytes_size(self) -> int:
        largest_ad_bytes_count = 0
        for ad in self.ads:
            if ad.size() > largest_ad_bytes_count:
                largest_ad_bytes_count = ad.size()

        # Return which ever is smaller:
        # - Num bytes in music + 10% extra buffer (for ads).
        # - Num bytes in music + num bytes in the largest ad.
        music_and_largest_ad_bytes_count = self.music_track.size() + largest_ad_bytes_count
        music_and_ten_percent_more_bytes_count = int(self.music_track.size() * 1.1)
        if music_and_largest_ad_bytes_count <= music_and_ten_percent_more_bytes_count:
            return music_and_largest_ad_bytes_count
        return music_and_ten_percent_more_bytes_count

