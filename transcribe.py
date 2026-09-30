import sys
import os
from faster_whisper import WhisperModel

def transcribe(mp3_path, model_size="tiny"):
    print(f"Loading model '{model_size}'...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    print(f"Transcribing: {mp3_path}")
    segments, info = model.transcribe(
        mp3_path,
        beam_size=1,
        language="en",
        vad_filter=True,           # skips silence, big speedup
        vad_parameters=dict(min_silence_duration_ms=500)
    )
    out_lines = []
    for seg in segments:
        line = f"[{seg.start:6.1f}s] {seg.text.strip()}"
        print(line)
        out_lines.append(line)
    out_path = os.path.splitext(mp3_path)[0] + ".txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines))
    print(f"\nSaved: {out_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python transcribe.py <mp3>")
        sys.exit(1)
    transcribe(sys.argv[1])