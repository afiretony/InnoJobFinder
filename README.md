# InnoJobFinder — an automated job-search pipeline you run locally

InnoJobFinder scrapes fresh job postings, scores each one against **your** resume,
buckets them into role categories, and drafts tailored application material with
Claude — a bespoke one-page CV and cold-email draft for your strongest matches,
and one reusable per-category CV for the rest. Everything lands in a local folder
and a web dashboard.

**It never sends or submits anything.** It writes drafts to disk for you to
review, edit, and send yourself.

```
scrape (LinkedIn + Indeed via jobspy)      every run, deduped into SQLite
  └─> score 0-10 vs resume/profile.md      claude -p (cheap/fast model)
       └─> classify into role categories   (cheap/fast model)
            └─> score >= min_score: bespoke tailored CV + cold email   (stronger model)
                lower scores:        one reusable CV per category
                 └─> digest to output/INBOX.md + dashboard
```

## What you provide

The pipeline builds on your own resume material, kept in `resume/`:

- **`resume/profile.md`** — a plain-text source of truth for your experience.
  The matcher reads it to score jobs; the tailoring agent will never claim
  anything not written here.
- **`resume/cv.tex`** — a polished one-page LaTeX CV. The tailoring agent copies
  this and reshapes the copy per job; it never edits the base.

The repo ships a **fictional example** (Jordan Doe) so it runs immediately.
Replace both files with your own before relying on the output.

## Requirements

- **Python 3.10+** (3.12 recommended)
- **The `claude` CLI** on your PATH, authenticated (Claude subscription or API
  key). The pipeline calls it headlessly for scoring and tailoring.
- **`pdflatex`** (TeX Live / MacTeX) to compile CVs
- **`pdftoppm`** (poppler-utils) for the dashboard's inline PDF preview

```bash
# Debian/Ubuntu
sudo apt install texlive-latex-recommended texlive-fonts-recommended poppler-utils
# macOS
brew install --cask mactex-no-gui && brew install poppler
```

## Quickstart

```bash
git clone <your-fork-url> InnoJobFinder && cd InnoJobFinder
python -m venv .venv && .venv/bin/pip install -r requirements.txt

# 1. Make it yours
#    - edit resume/profile.md and resume/cv.tex with your real experience
#    - edit config.yaml: set candidate.name and search.terms

make scan     # scrape + score only (no CV generation) — a safe first run
make web      # dashboard at http://127.0.0.1:8765
make run      # full pipeline: scrape, score, classify, tailor top matches, digest
```

Model calls cost tokens/quota. `make scan` skips the expensive tailoring step;
use it while you dial in your profile and search terms. `tailoring.max_per_run`
caps how many bespoke CVs a full run produces.

## How matches are tiered

- **`matching.threshold`** (default 5) — score at or above this marks a job
  `matched` (worth applying to).
- **`tailoring.min_score`** (default 8) — a `matched` job at or above this gets a
  **bespoke** tailored CV + cold email (the expensive model).
- Matched jobs **below** `min_score` are served by their category's **generic**
  CV: one reusable, per-category CV you build with `make generic-cvs`.

Categories are a closed set you control in `config.yaml` (`forward_deployed`,
`ai_llm_engineer`, `inference_optimization`, `fullstack_product`,
`robotics_perception`, `ml_research`, `general_swe` by default). Rename or
extend them to fit your search.

## Dashboard

```bash
make web    # http://127.0.0.1:8765
```

Filter jobs by status and **by category**, read the fit reasoning and full JD,
preview the tailored CV inline, copy the cold-email draft, trigger a tailor or a
full scan, and mark jobs applied or dismissed. It also shows live progress of any
run (including scheduled ones).

> **Security:** the dashboard has **no authentication**. It binds `127.0.0.1`
> (loopback) by default. Only expose it wider (`JOBFINDER_HOST=0.0.0.0`) on a
> network you trust, and put an authenticating reverse proxy in front of any
> public access.

## Commands

```bash
make run          # full pipeline once (look-back from config)
make backfill     # catch-up scan over the last 24h
make scan         # scrape + score only, no CV generation
make list         # jobs by score
make tailor       # tailor from the match queue (capped by max_per_run)
make classify     # assign a category to unclassified jobs
make generic-cvs  # build the reusable per-category CVs
make test         # run the test suite
make web          # dashboard

.venv/bin/python -m jobfinder tailor <id>   # tailor one specific job
.venv/bin/python -m jobfinder show <id>     # full record for one job
```

Job status flow in `data/jobs.db`: `new -> scored | matched -> tailored | error`
(`duplicate` = same company+title seen from another site; `applied` / `dismissed`
are set by you in the dashboard).

## Configuration — `config.yaml`

- `candidate.name` — sets the filename prefix of generated CVs.
- `paths` — where your resume material and outputs live (relative paths resolve
  against the project root; absolute paths let you keep your resume in a separate
  repo).
- `search.terms` — queries grouped by role family. Edit freely.
- `matching.threshold` / `tailoring.min_score` — the tiering knobs above.
- `matching.model` / `tailoring.model` — which Claude models to use.
- `tailoring.max_per_run` — cap on bespoke CVs per run (keeps a run short enough
  to finish inside your schedule period; see `deploy/`).
- `tailoring.deemphasize_project` — optionally keep one flagship project off the
  generic CVs for categories that don't value it.

## Running on a schedule

See [`deploy/`](deploy/) for systemd user units (runs every 2 hours) and a cron
one-liner.

## Notes and limitations

- **Nothing is ever sent or submitted.** Review every CV and email before using
  it. The tailoring agent follows honesty rules (it won't invent experience) but
  it runs non-interactively — always check the PDF.
- The score is a fast heuristic from a small model; it occasionally over- or
  under-rates a posting. The category (read from the JD) is a useful cross-check.
- ZipRecruiter blocks scrapers (403). Glassdoor/Google can be added in
  `search.sites` but are flaky. LinkedIn guest endpoints can rate-limit; failed
  terms are logged and retried on the next run (the look-back window overlaps).

## License

MIT — see [LICENSE](LICENSE).
