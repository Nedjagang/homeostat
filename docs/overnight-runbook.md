# Running ClaimPilot overnight (autonomous telemetry generation)

Two processes make an overnight run worth analyzing:

1. **The service** (`claimpilot/control.py`) — continuous claims through the agent + eval
   funnel, exporting traces/metrics/logs.
2. **The overnight scheduler** (`chaos/overnight.py`) — drives `/control` on a 3-hour
   cycle: healthy baseline → a stretch on `v2_concise` (second good version in the
   prompt history) → a 20-min prompt regression + heal (SLO alert fires and resolves) →
   a 10-min broken-tool incident + circuit-breaker heal. ~4 faithfulness incidents and
   ~4 tool incidents per 12 h, each with a clean recovery edge.

## Cost knob (read before starting)

Each claim = 1 agent call + usually 1 judge call on a reasoning-class deployment. The
loop is serial: real pace ≈ claim latency (~30 s) + `CLAIM_INTERVAL_SECONDS` (jittered).

| `CLAIM_INTERVAL_SECONDS` | ≈ claims / 12 h | Use |
|---|---|---|
| 45 (overnight default) | ~550–650 | overnight analysis density |
| 20 (daytime default) | ~900–1000 | demo density |
| 120 | ~250 | budget-safe soak |

## Option A — this laptop, detached processes (works tonight, zero new infra)

Everything runs on the host (venv + Windows cert store + VPN already proven). The
processes are fully detached — they survive the terminal/Claude session ending.

```powershell
# 1. keep the laptop awake on AC power (0 = never sleep; monitor may still turn off)
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0

# 2. the service (detached; logs outside OneDrive to avoid sync churn)
New-Item -ItemType Directory -Force "$env:LOCALAPPDATA\claimpilot" | Out-Null
$repo = "C:\Users\pp\OneDrive - Aptean-online\Desktop\signoz"
Start-Process -WindowStyle Hidden -WorkingDirectory "$repo\homeostat\claimpilot" `
  -FilePath "$repo\.venv\Scripts\python.exe" `
  -ArgumentList "-m","uvicorn","control:app","--port","8091","--host","127.0.0.1" `
  -RedirectStandardOutput "$env:LOCALAPPDATA\claimpilot\service.log" `
  -RedirectStandardError  "$env:LOCALAPPDATA\claimpilot\service.err.log" `
  -Environment @{ CLAIM_INTERVAL_SECONDS = "45" }

# 3. the overnight scheduler (detached)
Start-Process -WindowStyle Hidden -WorkingDirectory "$repo\homeostat" `
  -FilePath "$repo\.venv\Scripts\python.exe" `
  -ArgumentList "chaos\overnight.py" `
  -RedirectStandardOutput "$env:LOCALAPPDATA\claimpilot\overnight.log" `
  -RedirectStandardError  "$env:LOCALAPPDATA\claimpilot\overnight.err.log"

# check on it anytime
curl.exe -s http://127.0.0.1:8091/control/state
Get-Content "$env:LOCALAPPDATA\claimpilot\overnight.log" -Tail 20

# stop both in the morning
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
  Where-Object { $_.CommandLine -match 'uvicorn control:app|overnight\.py' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Known risks (accept or use Option B): laptop must stay powered on; if corporate
VPN/network drops overnight, telemetry export pauses (the service keeps running, OTel
retries then drops — you get a gap, not a crash) and the scheduler keeps cycling locally.

## Option B — the SigNoz Azure VM (durable, the target architecture)

The VM runs 24/7 and the containers talk to the collector over the docker network —
no VPN, no laptop, no TLS-trust question. This is also where the brain will live.

```bash
# on the VM (adjust the network name to the SigNoz stack's; `docker network ls`)
git clone <homeostat repo> && cd homeostat
cp claimpilot/.env.example claimpilot/.env   # fill: Azure keys, CLAIMPILOT_CONTROL_TOKEN
# in claimpilot/.env set: OTEL_EXPORTER_OTLP_ENDPOINT=http://signoz-ingester:4318  (or the
# stack's collector container name), CLAIM_INTERVAL_SECONDS=45
docker compose -f docker-compose.apps.yaml up --build -d claimpilot
# scheduler (simplest: host python next to it)
nohup python3 chaos/overnight.py > overnight.log 2>&1 &
```

`restart: unless-stopped` keeps the service alive across container crashes and VM
reboots. Port 8091 stays VM-internal (flip flags from the VM shell or an SSH tunnel —
no public exposure needed).

## What to analyze in the morning (SigNoz side)

- **Alerts → triggered history**: 4+ fire/resolve cycles on "Faithfulness SLO fast
  burn"; check time-to-fire vs. the scheduler's injection timestamps (overnight.log).
- **Metrics**: `gen_ai.evaluation.score` avg + `gen_ai.evaluation.verdicts` grounded
  ratio over 12 h — square-wave incident shapes; group by `prompt.version` for the
  three-version history; `gen_ai.usage.cost` / `gen_ai.evaluation.judge_tokens` for the
  cost story; `claimpilot.claims.processed{outcome=error}` spikes during tool windows.
- **Traces**: spans where `gen_ai.evaluation.score.value < 0.5` — hundreds of lying
  spans with prompts + judge explanations attached; `homeostat.action` spans marking
  every injection and heal.
- **Logs**: WARN `unsupported answer` ↔ span pivots; `gen_ai.evaluation.result` events.
