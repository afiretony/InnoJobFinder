PY = .venv/bin/python

# Full pipeline once, now (default 3h look-back from config)
run:
	$(PY) -m jobfinder run

# First-time / catch-up scan over the last 24h
backfill:
	$(PY) -m jobfinder run --hours 24

# Scan + score only; skip CV generation
scan:
	$(PY) -m jobfinder run --no-tailor

# List recent jobs by score
list:
	$(PY) -m jobfinder list

# Tailor from the match queue, capped by tailoring.max_per_run
tailor:
	$(PY) -m jobfinder tailor

# Assign a category to every unclassified job (Haiku, cheap)
classify:
	$(PY) -m jobfinder classify

# Build the reusable per-category CVs (Opus — one run per category)
generic-cvs:
	$(PY) -m jobfinder generic-cvs

# Run the test suite
test:
	$(PY) -m pytest tests/ -q

# Local dashboard at http://127.0.0.1:8765
web:
	$(PY) -m jobfinder.web

# Tail today's run log (see deploy/ for running on a schedule)
status:
	@tail -n 20 logs/run_$$(date +%Y%m%d).log 2>/dev/null || echo "(no log today — run 'make run')"

.PHONY: run backfill scan list tailor classify generic-cvs test web status
