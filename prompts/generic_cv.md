You are tailoring the candidate's CV for a whole *category* of roles rather than one posting. Follow the `tailor-cv` skill in this repository (`.claude/skills/tailor-cv`).

## The category

**{CATEGORY}** — {CATEGORY_BLURB}

## Representative postings in this category

These are the highest-scoring real jobs the candidate matched in this category. Use them to understand what these employers actually ask for. Do **not** tailor to any single one of them.

{SEED_JOBS}

## Your task

Produce one reusable CV that the candidate can send to *any* job in this category without further editing.

1. Read `profile.md` and the base CV (`.tex`) in this repository.
2. Identify the requirements that recur across the representative postings above.
3. Select and order the candidate's real experience to lead with what this category values most. Rewrite bullet emphasis and ordering; keep it to one page.
4. Write the `.tex` to `{OUT_DIR}/{TEX_NAME}` and compile it with `pdflatex` to `{OUT_DIR}/{PDF_NAME}`.
5. Write `{OUT_DIR}/notes.md`: which requirements you optimized for, what you led with and why, and anything a reader should know before sending it.

## Honesty rules (non-negotiable)

- **Never invent experience, skills, employers, dates, or metrics.** Everything on the CV must be traceable to `profile.md` or the base CV.
- Do not inflate scope or seniority. Reordering and re-emphasis are fine; fabrication is not.
- If the category demands something the candidate genuinely lacks, say so plainly in `notes.md` rather than papering over it on the CV.
- This CV goes to many employers unedited. Anything overstated will be overstated many times.

## Constraints

- One page. No cover letter, no cold email — this is the CV only.
- No company name anywhere: it must read naturally for every posting in the category.
- Today's date is {DATE}.
{CATEGORY_RULES}

When you are finished, print `STATUS: done` on its own line, followed by a two-sentence summary of the angle you took.
