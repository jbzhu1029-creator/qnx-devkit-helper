"""Mix a Piper voiceover of demo/narration.md onto the VHS capture.

The spoken text is the narration. A few tokens are respelled so the
synthesizer says the initials instead of a mashed word (QEMU was "kemu").
Subtitles keep the original sentences. Cue times are the narration
headings, shifted so they start when the "qnxdoctor faceless demo"
banner is on screen.

Nothing here runs qnxdoctor differently, and nothing talks to a real
SDP install or QEMU.
"""

from __future__ import annotations

import argparse
import array
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

# Longer tokens first so a short replacement cannot eat part of a longer one.
SPOKEN_REPLACEMENTS = (
    ("gcc_ntoaarch64le", "G C C N T O A arch 64 little endian"),
    ("gcc_ntox86_64", "G C C N T O x 86 64"),
    ("nto-aarch64-o-be", "N T O A arch 64 big endian"),
    ("nto-armv7-o-le", "N T O arm v 7 little endian"),
    ("qnxsdp-env.sh", "the Q N X S D P env script"),
    ("demo/mock-env.sh", "demo mock env shell script"),
    ("--require-sdp", "the require S D P flag"),
    ("missing-toolchain", "missing toolchain"),
    ("QEMU", "Q E M U"),
    ("epoll", "e poll"),
)

# Leave this much quiet time before the next cue when a clip is shortened.
TAIL_GAP = 0.40
# Piper at length 1.0 already matches the slots. Above this, the section
# is too long for the gap and the script stops instead of sounding rushed.
MAX_TEMPO = 1.22
SAMPLE_RATE = 22050


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True, help="silent VHS capture")
    parser.add_argument("--narration", type=Path, required=True)
    parser.add_argument("--piper", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="narrated mp4")
    parser.add_argument("--srt", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True, help="scratch directory")
    parser.add_argument("--banner-offset", type=float, default=None)
    args = parser.parse_args(argv)

    video_duration = probe_duration(args.video)
    if video_duration >= 180:
        raise SystemExit(f"capture is {video_duration:.1f}s, which is not under 3 minutes")
    if video_duration < 90:
        raise SystemExit(f"capture is only {video_duration:.1f}s; the tape sleep did not record")

    sections = spoken_sections(args.narration.read_text(encoding="utf-8"))
    if len(sections) < 2:
        raise SystemExit(f"no narration cues in {args.narration}")

    banner = args.banner_offset
    if banner is None:
        banner = detect_banner_offset(args.video)
    print(f"banner at {banner:.2f}s, capture {video_duration:.2f}s")

    args.work.mkdir(parents=True, exist_ok=True)
    clips: list[tuple[float, array.array]] = []
    cue_spans: list[tuple[float, float, str]] = []
    for index, (at, paragraph) in enumerate(sections):
        start = banner + at
        if index + 1 < len(sections):
            slot_end = banner + sections[index + 1][0]
        else:
            slot_end = video_duration - 0.2
        slot = slot_end - start
        if slot <= 1:
            raise SystemExit(f"cue at {at}s has no room before the next event")
        speech = speakable(paragraph)
        wav_path = args.work / f"cue-{index:02d}.wav"
        synthesize(args.piper, args.model, speech, wav_path)
        samples = read_wav(wav_path)
        samples = trim_tail(samples)
        duration = len(samples) / SAMPLE_RATE
        tempo = 1.0
        if duration > slot - TAIL_GAP:
            tempo = duration / (slot - TAIL_GAP)
            if tempo > MAX_TEMPO:
                raise SystemExit(
                    f"cue at {at}s is {duration:.1f}s of speech in a {slot:.1f}s gap "
                    f"(would need tempo {tempo:.2f})"
                )
            sped = args.work / f"cue-{index:02d}-fit.wav"
            apply_tempo(wav_path, sped, tempo)
            samples = trim_tail(read_wav(sped))
            duration = len(samples) / SAMPLE_RATE
        stamp = f"{at // 60}:{at % 60:02d}"
        print(
            f"  {stamp}  start {start:6.2f}s  speech {duration:5.2f}s  "
            f"slot {slot:5.2f}s  tempo {tempo:.2f}"
        )
        clips.append((start, samples))
        cue_spans.extend(subtitle_cues(paragraph, start, duration))

    bed = mix(clips, video_duration)
    narration_wav = args.work / "narration.wav"
    write_wav(narration_wav, bed)
    write_srt(args.srt, cue_spans)
    mux(args.video, narration_wav, args.output, video_duration)
    report = inspect_output(args.output)
    print(
        f"wrote {args.output}  {report['duration']:.2f}s  "
        f"{report['width']}x{report['height']}  "
        f"mean {report['mean_volume']}"
    )
    return 0


def spoken_sections(text: str) -> list[tuple[int, str]]:
    """Return (seconds, paragraph) for each '## m:ss' heading."""

    sections: list[tuple[int, str]] = []
    current: int | None = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections.append((current, _paragraph(buf)))
            stamp = line[3:].strip()
            minutes, seconds = stamp.split(":")
            current = int(minutes) * 60 + int(seconds)
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections.append((current, _paragraph(buf)))
    return sections


def _paragraph(lines: list[str]) -> str:
    return " ".join(line.strip() for line in lines if line.strip())


def speakable(text: str) -> str:
    spoken = text
    for source, replacement in SPOKEN_REPLACEMENTS:
        spoken = spoken.replace(source, replacement)
    return spoken


def synthesize(piper: Path, model: Path, text: str, dest: Path) -> None:
    completed = subprocess.run(
        [
            str(piper),
            "--model",
            str(model),
            "--output_file",
            str(dest),
            "--sentence_silence",
            "0.14",
            "--length_scale",
            "1.0",
            "--noise_scale",
            "0.667",
            "--noise_w",
            "0.8",
        ],
        input=text + "\n",
        text=True,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0 or not dest.exists():
        sys.stderr.write(completed.stderr)
        raise SystemExit(f"piper failed for: {text[:80]}")


def read_wav(path: Path) -> array.array:
    with wave.open(str(path)) as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise SystemExit(f"{path} is not mono 16-bit")
        if handle.getframerate() != SAMPLE_RATE:
            raise SystemExit(f"{path} is {handle.getframerate()} Hz, expected {SAMPLE_RATE}")
        samples = array.array("h")
        samples.frombytes(handle.readframes(handle.getnframes()))
    return samples


def trim_tail(samples: array.array, keep_s: float = 0.08, threshold: int = 400) -> array.array:
    last = 0
    for index, sample in enumerate(samples):
        if abs(sample) > threshold:
            last = index
    end = min(len(samples), last + int(keep_s * SAMPLE_RATE) + 1)
    return samples[:end]


def apply_tempo(source: Path, dest: Path, tempo: float) -> None:
    completed = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(source),
            "-filter:a",
            f"atempo={tempo:.4f}",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "1",
            str(dest),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        raise SystemExit("ffmpeg atempo failed")


def mix(clips: list[tuple[float, array.array]], duration: float) -> array.array:
    total = int(duration * SAMPLE_RATE)
    bed = array.array("h", bytes(total * 2))
    fade = int(0.015 * SAMPLE_RATE)
    for start, samples in clips:
        offset = int(round(start * SAMPLE_RATE))
        if offset < 0:
            raise SystemExit("a narration cue starts before the video")
        for index, sample in enumerate(samples):
            position = offset + index
            if position >= total:
                break
            if index < fade:
                sample = int(sample * (index / fade))
            mixed = bed[position] + sample
            if mixed > 32767:
                mixed = 32767
            elif mixed < -32768:
                mixed = -32768
            bed[position] = mixed
    return bed


def write_wav(path: Path, samples: array.array) -> None:
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(samples.tobytes())


def subtitle_cues(paragraph: str, start: float, duration: float) -> list[tuple[float, float, str]]:
    sentences = re.split(r"(?<=[.!?])\s+", paragraph.strip())
    blocks: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if sentence:
            blocks.extend(wrap_blocks(sentence))
    if not blocks:
        return []
    weights = [max(1, len(block.replace("\n", " ").split())) for block in blocks]
    total = sum(weights)
    cues: list[tuple[float, float, str]] = []
    cursor = start
    consumed = 0
    for index, (block, weight) in enumerate(zip(blocks, weights)):
        consumed += weight
        end = start + duration if index == len(blocks) - 1 else start + duration * (consumed / total)
        cues.append((cursor, max(end, cursor + 0.3), block))
        cursor = end
    return cues


def wrap_blocks(text: str, width: int = 44, max_lines: int = 2) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if current and len(trial) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return ["\n".join(lines[index : index + max_lines]) for index in range(0, len(lines), max_lines)]


def write_srt(path: Path, cues: list[tuple[float, float, str]]) -> None:
    chunks: list[str] = []
    for index, (start, end, text) in enumerate(cues, start=1):
        chunks.append(f"{index}\n{_timestamp(start)} --> {_timestamp(end)}\n{text}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(chunks) + "\n", encoding="utf-8")


def _timestamp(seconds: float) -> str:
    millis = max(0, int(round(seconds * 1000)))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def detect_banner_offset(video: Path) -> float:
    """First time the lines under the prompt light up with the banner.

    The crop sits just below a one-line prompt on a 720p frame, which is
    where `qnxdoctor faceless demo` is printed. Typing the command stays
    on the prompt line and does not trip it.
    """

    fps = 10
    width, height = 320, 24
    completed = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(video),
            "-t",
            "12",
            "-vf",
            f"fps={fps},crop=w=iw*9/10:h=ih/10:x=iw/50:y=ih*45/1000,scale={width}:{height}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr.decode("utf-8", "replace"))
        raise SystemExit("could not read frames to find the demo banner")
    frame_size = width * height
    count = len(completed.stdout) // frame_size
    if count < 5:
        raise SystemExit("capture is too short to find the demo banner")
    means: list[float] = []
    for index in range(count):
        frame = completed.stdout[index * frame_size : (index + 1) * frame_size]
        means.append(sum(frame) / frame_size)
    baseline = min(means[:3])
    # A line of terminal text lifts this band by about 7. The threshold sits
    # under that and well above a blinking cursor in an empty band.
    for index, mean in enumerate(means):
        if mean > baseline + 5 and index + 1 < count and means[index + 1] > baseline + 5:
            return index / fps
    raise SystemExit(
        "could not find the 'qnxdoctor faceless demo' banner in the first 12 seconds"
    )


def mux(video: Path, narration: Path, dest: Path, duration: float) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(".partial.mp4")
    completed = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-i",
            str(narration),
            "-filter:a",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            f"{duration:.3f}",
            "-movflags",
            "+faststart",
            str(partial),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        partial.unlink(missing_ok=True)
        raise SystemExit("ffmpeg mix failed")
    partial.replace(dest)


def probe_duration(path: Path) -> float:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        raise SystemExit(f"ffprobe failed for {path}")
    return float(json.loads(completed.stdout)["format"]["duration"])


def inspect_output(path: Path) -> dict[str, object]:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    payload = json.loads(completed.stdout)
    streams = payload["streams"]
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    if not any(stream["codec_type"] == "audio" for stream in streams):
        raise SystemExit("narrated video has no audio stream")
    width = int(video["width"])
    height = int(video["height"])
    if (width, height) != (1280, 720):
        raise SystemExit(f"video is {width}x{height}, expected 1280x720")
    duration = float(payload["format"]["duration"])
    if duration >= 180:
        raise SystemExit(f"video is {duration:.1f}s, which is not under 3 minutes")
    volume = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    match = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", volume.stderr)
    if match is None:
        raise SystemExit("could not measure narration loudness")
    mean = float(match.group(1))
    if mean < -30:
        raise SystemExit(f"narration is too quiet (mean {mean:.1f} dB)")
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "mean_volume": f"{mean:.1f} dB",
    }


if __name__ == "__main__":
    raise SystemExit(main())
