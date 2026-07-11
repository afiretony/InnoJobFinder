You are running HEADLESSLY (no user available) inside the candidate's resume repo. Your task: produce a tailored one-page CV and a cold email draft for the job below.

## Job

- Title: {TITLE}
- Company: {COMPANY}
- Location: {LOCATION}
- URL: {URL}
- Match score: {SCORE}/10 ({FIT})

### Full job description

{DESCRIPTION}

## Instructions

1. Read `.claude/skills/tailor-cv/SKILL.md` in this repo and follow its workflow, honesty rules, style rules (NO em-dashes anywhere, including the email), and one-page LaTeX recipe EXACTLY, with one exception: SKIP the user-confirmation step. You cannot ask questions. Make best-judgment selections yourself and be conservative: when a claim is borderline, drop it. Never fabricate anything.
2. Company slug: derive a short brand name from "{COMPANY}" (e.g. "Applied Intuition" -> AppliedIntuition). Today's date: {DATE}.
3. Generate the tailored CV at `tailored/<Company>/{CV_PREFIX}_<Company>_<Job-Title>_{DATE}.tex`, compile it twice from the repo root per the skill, and confirm ONE page via the .log file. Fix overfull hboxes and page overflows before finishing.
4. Copy the final PDF into the application folder: `cp tailored/<Company>/<basename>.pdf {APP_DIR}/`
5. Write `{APP_DIR}/cold_email.md` — a cold outreach email draft:
   - Start with a metadata block: recipient line `To: [find - recruiter or hiring manager at {COMPANY}]`, a suggested subject line, and the job URL.
   - Never fabricate claims. Do not invent the recipient's name.

{EMAIL_STYLE}
6. Write `{APP_DIR}/notes.md`: the JD's top requirements, which experiences you led with and why, what you cut, and HONEST GAPS (requirements the candidate does not clearly meet) to address or avoid overclaiming.
7. Your FINAL message must be exactly these lines (machine-parsed):
PDF: <absolute path of the PDF inside {APP_DIR}>
TEX: <absolute path of the .tex in tailored/>
PAGES: <page count from the .log>
STATUS: done
