---
name: tailor-cv
description: "Generate a one-page resume/CV tailored to a specific job description, derived from the candidate's polished base CV (resume/cv.tex) with resume/profile.md as the supplementary fact source, rendered with pdflatex. Use whenever a JD (a URL or pasted text) is supplied and a customized resume/CV is wanted. The skill analyzes the JD (required vs preferred qualifications, ATS keywords, honest gaps), selects which experiences to feature, then generates and compiles a tailored one-page PDF. It never fabricates experience, skills, titles, employers, or metrics."
---

# Tailor CV to a Job Description

Given a job description, produce a **one-page, ATS-friendly CV tailored to that JD**, derived from the candidate's polished base CV and verified against their profile.

## Source files (in the resume working dir)

- **`cv.tex`** — the **BASE**: the polished, one-page canonical resume. **Start every tailored CV by copying this file**, then reshape the copy to the JD. Its wording, metrics, and layout are already refined — reuse them; don't rewrite from scratch.
- **`profile.md`** — the **fuller source of truth** for facts NOT in the base CV (extra roles, projects, metrics, dates). Pull relevant experiences from here when the JD needs them, and verify any claim against it. Anything not in `cv.tex` or `profile.md` must not appear on the CV.
- **`tailored/<Company>/`** — every company-specific CV lives in its own subfolder here (never flat in the repo root).
- Build with `pdflatex` (must be on PATH). Render a page to PNG with `pdftoppm` (poppler) for a visual check.

## Workflow

### 1. Get and analyze the JD
- If given a **URL**, fetch it. If **pasted text**, use it directly.
- Extract briefly: (a) the role in one sentence; (b) **required** qualifications; (c) **preferred / nice-to-have**; (d) hard **ATS keywords** (tools, frameworks, methods); (e) **logistics** (location, travel, on-site); (f) the company's vocabulary/tone to mirror.

### 2. Read the base CV, then the profile
- Read **`cv.tex`** in full first (your starting material). Then read **`profile.md`** for facts/experiences the base doesn't cover.

### 3. Build the JD → evidence map (internal)
- For each **required** and key **preferred** item, find the strongest matching evidence — first in the base CV, then in `profile.md`. Note which base bullets to **keep/reorder/trim**, which extra experiences to **pull in**, what to **cut**, and the **honest gaps** (requirements with no real evidence).
- Reframe the identity to match the role — but only by re-emphasizing real work, never by inventing it.

### 4. Confirm with the user (interactive use only)
When a user is present, present the JD's essence and your proposed mapping, and ask 2–4 focused questions (which experiences to feature, how to handle thin areas, borderline claims). **When running headless/non-interactively, skip this step**: make conservative best-judgment selections yourself and drop any borderline claim.

### 5. Generate the tailored `.tex` by adapting the base
- Copy the base into the company subfolder, then edit the copy:
  `mkdir -p tailored/<Company> && cp cv.tex tailored/<Company>/<CV-basename>.tex`
  - `<Company>`: short brand (e.g. `Acme`). For staffing/contract roles, use the end client.
  - `<CV-basename>`: follow the naming pattern given by the caller (typically `<Prefix>_<Company>_<Job-Title>_<YYYY-MM-DD>`), a hyphenated role slug, no spaces/slashes/parens.
- Reshape the copy to the JD:
  - **Summary** — rewrite to mirror the JD's language and lead identity. Identity, scope, and impact; not a tech-stack list.
  - **Experience** — prefer selecting, reordering, and trimming the base's pre-vetted bullets over rephrasing them. Pull in extra experiences from `profile.md` when relevant. Every bullet should state impact (what shipped/improved/enabled), not just activity.
  - **Skills** — reorder so the JD's required stack leads; add JD-relevant real skills, drop irrelevant ones. Don't orphan a skill from a cut experience.
- Add a logistics line (e.g. "open to relocation") only when it's true.

### 6. Compile to ONE page and QA
- Compile twice (so cross-references/layout settle):
  `pdflatex -interaction=nonstopmode -halt-on-error -output-directory=tailored/<Company> tailored/<Company>/<CV-basename>.tex` (run it, then run it again).
- The line `Output written on … (N pages …)` in the `.log` is the authority on page count. If it's not exactly 1 page, tighten (list `itemsep`, font leading, margins) or cut the least-relevant bullet, and recompile.
- Optional visual check: `pdftoppm -png -singlefile -r 150 tailored/<Company>/<CV-basename>.pdf /tmp/cvcheck` then read `/tmp/cvcheck.png`. Confirm nothing clips the right margin and it isn't cramped.
- Resolve **Overfull \hbox** warnings (except a harmless centered contact line).

### 7. Report
- Summarize: what you led with and why (JD requirement → evidence), what you cut, and the **honest gaps** a reader should know before applying.

## Honesty rules (non-negotiable)
- Only use facts in `cv.tex`, `profile.md`, or explicitly confirmed by the user. **Never** invent metrics, skills, tools, titles, employers, dates, or scope. Keep the base CV's pre-vetted numbers intact; don't inflate or fabricate new ones.
- Surface required-but-missing qualifications plainly; don't paper over a gap on the CV.

## Style rules
- **Summary = identity, leadership, impact. Not a tech-stack dump.**
- **No em-dashes** (`---`). Use commas, colons, semicolons, parentheses, or a middle dot (`$\cdot$`) for separators. Hyphens in compound words and date ranges are fine.
- **Every bullet states impact, not just action.**
- No hard numbers unless the profile/base CV supports them.
- Borderline/adjacent claims: confirm with the user or drop them.

## One-page LaTeX tips
- **List spacing is the biggest vertical lever:** `itemsep`/`topsep` in `\setlist[itemize]{…}`. Reach for this before shrinking the font.
- **Font size and leading** are the next lever (document class option and `geometry` margins).
- **Don't chase the last line forever.** If ~1 line spills, free ~2 lines at once (shorten the longest/least-relevant bullet) rather than nudging leading repeatedly.
- Auxiliary `.aux/.log/.out` are gitignored.

## Scope
Produce **only** the tailored CV (a copy). Do not modify the base `cv.tex` or `profile.md` unless asked.
