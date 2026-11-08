"""Optional: transcribe the think-aloud recording locally into an .srt file.

    pip install faster-whisper
    python tools/transcribe.py session.mp4 -o transcript.srt [--language zh]

Any other transcription tool that exports .srt or .vtt works as well.
"""
import argparse
import sys


def stamp(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("media")
    parser.add_argument("-o", "--output", default="transcript.srt")
    parser.add_argument("--language", default=None, help="e.g. en or zh (default: detect)")
    parser.add_argument("--model", default="small", help="faster-whisper model size")
    args = parser.parse_args(argv)
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("Install faster-whisper first (pip install faster-whisper), or use any tool that exports .srt.")
        return 1
    segments, _info = WhisperModel(args.model).transcribe(args.media, language=args.language)
    with open(args.output, "w", encoding="utf-8") as out:
        for i, seg in enumerate(segments, 1):
            out.write("%d\n%s --> %s\n%s\n\n" % (i, stamp(seg.start), stamp(seg.end), seg.text.strip()))
    print("wrote", args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
