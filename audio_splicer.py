import os
import tempfile
import logging


import ffmpeg  # type: ignore
import mutagen.mp3
import mutagen.id3

from media_loader import StreamAndProbe

logger = logging.getLogger(__name__)

def _calculate_target_bitrate(duration_seconds: float, target_size_bytes: int) -> int:
    """
    Calculate target bitrate in bits/sec to achieve desired file size
    Includes some overhead for MP3 headers/metadata.
    """
    # Give ourselves ~5% overhead for MP3 headers/metadata.
    available_bytes = target_size_bytes * 0.95
    # Convert to bits per second (bytes * 8 bits/byte / seconds).
    target_bitrate = int((available_bytes * 8) / duration_seconds)
    # Return the first rate that's under our target.
    common_bitrates = [32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
    for rate in reversed(common_bitrates):
        if rate * 1000 <= target_bitrate:
            return rate
    assert False, "Bad args, target size is too small, fix callers"
    return 0

def _match_audio_params(
        stream,  # This is an ffmpeg.FilterableStream, but that type is not exposed.
        original_rate: int,
        original_channels: int,
        original_format: str,
        splits: int = 1,
): # We can't type the return type because the ffmpeg module doesn't expose it.
    """Apply audio parameter matching filters to a stream."""
    converted_stream = (stream
            .filter('aresample', original_rate)
            .filter('aformat',
                   sample_rates=original_rate,
                   sample_fmts=original_format,
                   channel_layouts=f'{original_channels}c'))
    if splits <= 1:
        return converted_stream
    return converted_stream.filter_multi_output('asplit', splits)


def insert_add(
        output_file_name: str,
        original_audio: StreamAndProbe,
        ad: StreamAndProbe,
        target_size_bytes: int,
) -> bool:
    mid_point = original_audio.duration() / 2
    ad_duration = ad.duration()
    fade_duration = 2

    # Get original audio parameters
    original_stream = original_audio.probe['streams'][0]
    original_rate = int(original_stream['sample_rate'])
    original_channels = int(original_stream['channels'])
    original_format = original_stream.get('sample_fmt', 's16')  # default to s16 if not specified

    # Check if parameters match
    ad_stream = ad.probe['streams'][0]
    needs_conversion = (
            int(ad_stream['sample_rate']) != original_rate or
            int(ad_stream['channels']) != original_channels or
            ad_stream.get('sample_fmt', 's16') != original_format
    )
    # needs_conversion = False
    if needs_conversion:
        ads = _match_audio_params(
                ad.stream.audio,
                original_rate,
                original_channels,
                original_format,
                3,
            )
    else:
        ads = [ad.stream.audio] * 3  # Expose original stream 3 times.

    # Calculate total duration and target bitrate
    total_duration = original_audio.duration() + ad_duration
    target_bitrate = _calculate_target_bitrate(total_duration, target_size_bytes)

    try:
        # Create first half (end slightly early for crossfade)
        first_half = (
            original_audio.stream
            .audio
            .filter('atrim', start=0, end=mid_point - fade_duration)
            .filter('asetpts', 'PTS-STARTPTS')
        )

        # Create fade-out portion of first half
        first_fade = (
            original_audio.stream
            .audio
            .filter('atrim', start=mid_point - fade_duration, end=mid_point)
            .filter('apad', whole_dur=fade_duration)
        )

        # Prepare insert audio's fade in
        insert_fade_in = (
            ads[0]
            .filter('atrim', start=0, end=fade_duration)
            .filter('asetpts', 'PTS-STARTPTS')
            .filter('apad', whole_dur=fade_duration)
        )

        # Create first crossfade
        first_crossfade = ffmpeg.filter(
            [first_fade, insert_fade_in],
            'acrossfade',
            d=fade_duration
        )

        # Get the main portion of insert audio (excluding fade regions)
        insert_main = (
            ads[1]
            .filter('atrim', start=fade_duration, end=ad_duration - fade_duration)
            .filter('asetpts', 'PTS-STARTPTS')
        )

        # Prepare insert audio's fade out
        insert_fade_out = (
            ads[2]
            .filter('atrim', start=ad_duration - fade_duration, end=ad_duration)
            .filter('asetpts', 'PTS-STARTPTS')
            .filter('apad', whole_dur=fade_duration)
        )

        # Create second half start (for fade in)
        second_fade = (
            original_audio.stream
            .audio
            .filter('atrim', start=mid_point, end=mid_point + fade_duration)
            .filter('asetpts', 'PTS-STARTPTS')
            .filter('apad', whole_dur=fade_duration)
        )

        # Create second crossfade
        second_crossfade = ffmpeg.filter(
            [insert_fade_out, second_fade],
            'acrossfade',
            d=fade_duration
        )

        # Get remainder of second half
        second_half = (
            original_audio.stream
            .audio
            .filter('atrim', start=mid_point + fade_duration, end=original_audio.duration())
            .filter('asetpts', 'PTS-STARTPTS')
        )

        # Concatenate all pieces
        streams = [first_half, first_crossfade, insert_main, second_crossfade, second_half]
        concat = ffmpeg.filter(streams, 'concat', n=len(streams), v=0, a=1)

        # Run the ffmpeg command
        out = ffmpeg.output(
            concat,
            output_file_name,
            write_xing=1,
            audio_bitrate=f"{target_bitrate}k",
            # Use VBR mode for better quality at target size
            qscale=0,
            # Ensure we don't exceed target bitrate
            maxrate=f"{target_bitrate}k",
            bufsize=f"{target_bitrate * 2}k",
        )

        print(out.compile())

        out.overwrite_output().run()

        return True

    except ffmpeg.Error as e:
        print(f"FFmpeg error occurred: {e}")
        return False


def pad_mp3_to_size(filename: str, target_size: int) -> bool:
    """
    Pad an MP3 file to exact size using ID3 padding.

    Args:
        filename: Path to MP3 file
        target_size: Desired size in bytes
    Returns:
        bool: True if padding succeeded, False if file is already too large
    """
    current_size = os.path.getsize(filename)
    logger.debug(f"Current file size: {current_size}")

    if current_size > target_size:
        logger.error(f"File already larger than target: {current_size} > {target_size}")
        return False

    # Calculate needed padding
    padding_needed = target_size - current_size
    logger.debug(f"Padding needed: {padding_needed}")

    try:
        # Load or create ID3
        try:
            tags = mutagen.id3.ID3(filename)
            logger.debug(f"Existing tag size: {tags.size}")
        except:
            tags = mutagen.id3.ID3()
            logger.debug("Created new ID3 tag")

        # Remove any existing padding frame
        if 'TXXX:padding' in tags:
            tags.pop('TXXX:padding')
            logger.debug("Removed existing padding frame")

        # Create exact-sized padding
        # Account for all frame overhead:
        # 10 bytes for frame header
        # Length of descriptor ('padding')
        # 1 byte for encoding
        # 1 byte for null terminator
        # Additional ID3 header bytes
        frame_overhead = (
                10 +  # Frame header
                len('padding') +  # Descriptor length
                1 +  # Encoding byte
                1 +  # Null terminator
                7 +  # ID3v2 tag header
                16 +  # Additional alignment/header bytes
                2  # Final 2 bytes (possibly frame footer or alignment)
        )
        logger.debug(f"Calculated frame overhead: {frame_overhead}")

        padding = b'\x00' * (padding_needed - frame_overhead)
        logger.debug(f"Created padding of length: {len(padding)}")

        # Add padding frame
        tags.add(mutagen.id3.TXXX(encoding=0, desc='padding', text=padding.decode('latin1')))

        # Save with minimal additional padding
        tags.save(filename, padding=lambda x: 0)

        # Verify final size
        final_size = os.path.getsize(filename)
        logger.debug(f"Final file size: {final_size}")

        if final_size != target_size:
            logger.error(f"Failed to achieve target size: got {final_size}, wanted {target_size}")
            return False

        return True

    except Exception as e:
        logger.error(f"Error padding file: {e}")
        return False

def insert_ad_and_pad(
        original_audio: StreamAndProbe,
        ad: StreamAndProbe,
        target_size_bytes: int,
) -> str:
    # Use a tempfile to ensure we get a unique name. We'll clean it up
    # manually, as this lets us return such files via FastAPI without
    # us/tempfile deleting the file from underneath FastAPI.
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp:
        print(f"Audio file name: {tmp.name}")
        insert_add(tmp.name, original_audio, ad, target_size_bytes)
        pad_mp3_to_size(tmp.name, target_size_bytes)
        return tmp.name