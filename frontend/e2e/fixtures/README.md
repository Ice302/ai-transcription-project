# Test fixtures

`standup.mp4`: 37 s, 1280×720, three slides, two synthetic voices (Windows SAPI *Zira* and *David*) taking turns. The script mixes jargon and names that speech models get wrong (Kubernetes, Grafana, Snowflake, Postgres, Terraform, Priya, Marcus Okafor), and the slides hold details that are never said aloud (ARR impact: 1.2M USD, the next sync date). Ground truth: six turns, Zira / David alternating, with slide changes at 13.1 s and 26.4 s.

To regenerate it on Windows:

```powershell
Add-Type -AssemblyName System.Speech
$lines = @(
  @("Microsoft Zira Desktop",  "Hi everyone, thanks for joining. Let's start with the Kubernetes migration status."),
  @("Microsoft David Desktop", "Sure. We moved forty services so far, and the Grafana dashboards are live for all of them."),
  @("Microsoft Zira Desktop",  "Great. What about the Snowflake costs? Finance asked about the quarterly numbers."),
  @("Microsoft David Desktop", "Costs dropped eighteen percent after we tuned the warehouses. Priya will send the full report."),
  @("Microsoft Zira Desktop",  "Perfect. Then the action items: Marcus migrates the Postgres cluster by Friday."),
  @("Microsoft David Desktop", "And I will schedule the Terraform review for next Tuesday.")
)
for ($i = 0; $i -lt $lines.Count; $i++) {
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $s.SelectVoice($lines[$i][0]); $s.Rate = 1
  $s.SetOutputToWaveFile("$PWD\line$i.wav"); $s.Speak($lines[$i][1]); $s.Dispose()
}
python make_standup_video.py .   # writes dialogue.mp4 (rename to standup.mp4), dialogue.wav and truth.json
```
