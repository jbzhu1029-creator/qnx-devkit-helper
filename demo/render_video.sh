#!/usr/bin/env bash
# Record demo/qnxdoctor.tape and mix a Piper voiceover of demo/narration.md.
#
# Writes demo/qnxdoctor-demo.mp4 and demo/qnxdoctor-demo.srt.
# The session is the mocked SDP tree from demo/mock-env.sh. It does not
# use a real qcc, a QNX install, or QEMU.
#
# Requires ffmpeg and Google Chrome or Chromium (VHS renders a headless
# browser). On Linux x86_64, VHS, ttyd, Piper, and the Lessac high voice
# are downloaded into demo/.render/ when they are not already available.
# Override with VHS, TTYD, PIPER, and PIPER_MODEL.

set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$ROOT"

VHS_VERSION=0.12.1
TTYD_VERSION=1.7.7
PIPER_VERSION=2023.11.14-2
VOICE_NAME=en_US-lessac-high
VOICE_URL=https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/high

RENDER="$ROOT/demo/.render"
TOOLS="$RENDER/tools"
mkdir -p "$TOOLS" "$RENDER/voices" "$RENDER/audio"

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "render_video.sh: $1 is required." >&2
    exit 1
  fi
}

need ffmpeg
need ffprobe
need python3
need curl

if ! command -v google-chrome >/dev/null 2>&1 \
  && ! command -v google-chrome-stable >/dev/null 2>&1 \
  && ! command -v chromium >/dev/null 2>&1 \
  && ! command -v chromium-browser >/dev/null 2>&1; then
  echo "render_video.sh: VHS needs Google Chrome or Chromium on PATH." >&2
  exit 1
fi

fetch() {
  local url=$1 dest=$2
  echo "fetching $url"
  curl -fL --retry 3 --retry-delay 2 -o "$dest" "$url"
}

if [[ -z "${VHS:-}" ]]; then
  if command -v vhs >/dev/null 2>&1; then
    VHS=$(command -v vhs)
  else
    case "$(uname -s)-$(uname -m)" in
      Linux-x86_64)
        deb="$TOOLS/vhs.deb"
        if [[ ! -x "$TOOLS/vhs-root/usr/bin/vhs" ]]; then
          fetch "https://github.com/charmbracelet/vhs/releases/download/v${VHS_VERSION}/vhs_${VHS_VERSION}_amd64.deb" "$deb"
          dpkg-deb -x "$deb" "$TOOLS/vhs-root"
        fi
        VHS="$TOOLS/vhs-root/usr/bin/vhs"
        ;;
      *)
        echo "render_video.sh: install VHS ${VHS_VERSION} and set VHS=." >&2
        exit 1
        ;;
    esac
  fi
fi

if [[ -z "${TTYD:-}" ]]; then
  if command -v ttyd >/dev/null 2>&1; then
    TTYD=$(command -v ttyd)
  else
    case "$(uname -s)-$(uname -m)" in
      Linux-x86_64)
        TTYD="$TOOLS/ttyd"
        if [[ ! -x "$TTYD" ]]; then
          fetch "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/ttyd.x86_64" "$TTYD"
          chmod +x "$TTYD"
        fi
        ;;
      *)
        echo "render_video.sh: install ttyd ${TTYD_VERSION} and set TTYD=." >&2
        exit 1
        ;;
    esac
  fi
fi

if [[ -z "${PIPER:-}" ]]; then
  if command -v piper >/dev/null 2>&1; then
    PIPER=$(command -v piper)
  else
    case "$(uname -s)-$(uname -m)" in
      Linux-x86_64)
        if [[ ! -x "$TOOLS/piper/piper" ]]; then
          archive="$TOOLS/piper.tar.gz"
          fetch "https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_x86_64.tar.gz" "$archive"
          tar -xzf "$archive" -C "$TOOLS"
        fi
        PIPER="$TOOLS/piper/piper"
        ;;
      *)
        echo "render_video.sh: install Piper ${PIPER_VERSION} and set PIPER=." >&2
        exit 1
        ;;
    esac
  fi
fi

if [[ -z "${PIPER_MODEL:-}" ]]; then
  PIPER_MODEL="$RENDER/voices/${VOICE_NAME}.onnx"
fi
if [[ ! -f "$PIPER_MODEL" ]]; then
  fetch "${VOICE_URL}/${VOICE_NAME}.onnx" "$PIPER_MODEL"
  fetch "${VOICE_URL}/${VOICE_NAME}.onnx.json" "${PIPER_MODEL}.json"
fi

export PATH="$(dirname "$TTYD"):$PATH"
# The upstream Piper tarball needs its own lib directory on the loader path.
export LD_LIBRARY_PATH="$(dirname "$PIPER")${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

CAPTURE="$RENDER/capture.mp4"
awk '
  /^Output / { print "Output demo/.render/capture.mp4"; next }
  { print }
' "$ROOT/demo/qnxdoctor.tape" > "$RENDER/qnxdoctor.tape"

"$VHS" validate "$RENDER/qnxdoctor.tape"
echo "recording demo/qnxdoctor.tape"
"$VHS" "$RENDER/qnxdoctor.tape"

python3 "$ROOT/demo/render_narration.py" \
  --video "$CAPTURE" \
  --narration "$ROOT/demo/narration.md" \
  --piper "$PIPER" \
  --model "$PIPER_MODEL" \
  --work "$RENDER/audio" \
  --srt "$ROOT/demo/qnxdoctor-demo.srt" \
  --output "$ROOT/demo/qnxdoctor-demo.mp4"

bytes=$(wc -c < "$ROOT/demo/qnxdoctor-demo.mp4")
limit=$((25 * 1024 * 1024))
if (( bytes > limit )); then
  echo "render_video.sh: demo/qnxdoctor-demo.mp4 is ${bytes} bytes, over the 25 MB cap." >&2
  echo "Re-encode the video track at a higher CRF and mix the narration again." >&2
  exit 1
fi

echo "demo/qnxdoctor-demo.mp4 is ${bytes} bytes"
echo "subtitles: demo/qnxdoctor-demo.srt"
echo "voice: Piper ${VOICE_NAME} (${PIPER_VERSION})"
