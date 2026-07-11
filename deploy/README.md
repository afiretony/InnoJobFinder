# Running InnoJobFinder on a schedule

The pipeline is a single command (`make run`, i.e. `python -m jobfinder run`).
Run it however you like; two common options:

## Option A — systemd user units (Linux)

Copy the units, adjusting `WorkingDirectory`/paths if you didn't clone to `~/InnoJobFinder`:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/jobfinder*.service deploy/systemd/jobfinder.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now jobfinder.timer        # runs every 2h
systemctl --user enable --now jobfinder-web.service  # dashboard
loginctl enable-linger "$USER"                       # survive logout/reboot
```

Logs: `journalctl --user -u jobfinder.service` and `logs/run_YYYYMMDD.log`.

> **Keep a run shorter than the timer period.** `Persistent=true` fires a missed
> run the moment the service goes idle, so if a run ever exceeds 2h the timer
> will back-to-back forever. `tailoring.max_per_run` bounds the slow phase — keep
> it low enough that a run finishes comfortably inside the period.

## Option B — cron (any Unix)

```cron
10 */2 * * * /path/to/InnoJobFinder/scripts/run_hourly.sh
```

`run_hourly.sh` derives its own paths and writes to `logs/`. Make sure the
`claude` CLI is on the PATH cron uses (it adds `~/.local/bin`).

## macOS (launchd)

Wrap `scripts/run_hourly.sh` in a `launchd` plist with `StartCalendarInterval`,
or just use cron. The dashboard's inline PDF preview needs `pdftoppm` (poppler);
install it with `brew install poppler`.
