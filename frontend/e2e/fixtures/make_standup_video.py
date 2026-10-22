"""Build a 3-slide, 2-speaker test meeting video from the SAPI line*.wav files.

Writes dialogue.mp4, dialogue.wav and truth.json (speaker turns + slide times) into the e2e2 dir.
"""
import json
import subprocess
import sys
import wave
from pathlib import Path

d = Path(sys.argv[1])
FONT = "C\\:/Windows/Fonts/arial.ttf"
GAP = 0.6
speakers = ["Zira", "David", "Zira", "David", "Zira", "David"]
slides = [
    ("Kubernetes Migration", ["40 services migrated", "Grafana dashboards live", "Owner: Priya Raghunathan"]),
    ("Snowflake Costs Q3", ["Warehouse tuning: -18% cost", "Report: Priya Raghunathan", "ARR impact: 1.2M USD"]),
    ("Action Items", ["Marcus Okafor: migrate Postgres cluster (Fri)", "Schedule Terraform review (Tue)", "Next sync: 2026-10-27"]),
]


def dur(p):
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def run(args):
    subprocess.run(args, check=True, capture_output=True)


t = 0.0
truth = {"turns": [], "slides": []}
segs = []
for k, (title, bullets) in enumerate(slides):
    a, b = d / f"line{2 * k}.wav", d / f"line{2 * k + 1}.wav"
    da, db = dur(a), dur(b)
    start = t
    truth["turns"].append({"speaker": speakers[2 * k], "start": round(t, 2), "end": round(t + da, 2)})
    t += da + GAP
    truth["turns"].append({"speaker": speakers[2 * k + 1], "start": round(t, 2), "end": round(t + db, 2)})
    t += db + GAP
    length = t - start
    truth["slides"].append({"title": title, "start": round(start, 2), "end": round(t, 2)})
    draw = [f"drawtext=fontfile='{FONT}':text='{title}':fontsize=64:fontcolor=white:x=80:y=110:expansion=none"]
    for i, line in enumerate(bullets):
        safe = line.replace(":", "\\:")
        draw.append(f"drawtext=fontfile='{FONT}':text='{safe}':fontsize=38:fontcolor=0xcbd5e1:x=80:y={290 + i * 70}:expansion=none")
    audio = d / f"slide{k}.wav"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(a), "-i", str(b), "-filter_complex",
         f"[0]apad=pad_dur={GAP}[x];[1]apad=pad_dur={GAP}[y];[x][y]concat=n=2:v=0:a=1[out]",
         "-map", "[out]", "-ar", "44100", "-ac", "1", str(audio)])
    out = d / f"slide{k}.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0x1e293b:s=1280x720:r=10:d={length:.3f}",
         "-i", str(audio), "-vf", ",".join(draw), "-t", f"{length:.3f}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-ar", "44100", str(out)])
    segs.append(out)

(d / "list.txt").write_text("".join(f"file '{s.name}'\n" for s in segs))
run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(d / "list.txt"), "-c", "copy", str(d / "dialogue.mp4")])
run(["ffmpeg", "-y", "-v", "error", "-i", str(d / "dialogue.mp4"), "-vn", "-ac", "1", "-ar", "16000", str(d / "dialogue.wav")])
(d / "truth.json").write_text(json.dumps(truth, indent=1))
print(json.dumps(truth, indent=1))
