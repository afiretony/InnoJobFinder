import logging

import pandas as pd
from jobspy import scrape_jobs

from . import db

log = logging.getLogger("jobfinder.scrape")


def _clean(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return str(val)


def run_scrape(conn, cfg: dict, hours_old: int | None = None) -> int:
    """Scrape all configured search terms; insert unseen jobs. Returns count of new jobs."""
    s = cfg["search"]
    hours = hours_old or s["hours_old"]
    new_count = 0

    for family, terms in s["terms"].items():
        for term in terms:
            kwargs = dict(
                site_name=s["sites"],
                search_term=term,
                location=s["location"],
                results_wanted=s["results_per_term"],
                hours_old=hours,
                country_indeed=s["country_indeed"],
                linkedin_fetch_description=s.get("linkedin_fetch_description", False),
                verbose=0,
            )
            if isinstance(s.get("is_remote"), bool):
                kwargs["is_remote"] = s["is_remote"]
            try:
                jobs = scrape_jobs(**kwargs)
            except Exception as e:
                log.warning("scrape failed for %r: %s", term, e)
                continue

            for _, row in jobs.iterrows():
                url = _clean(row.get("job_url"))
                if not url:
                    continue
                inserted = db.insert_job(
                    conn,
                    {
                        "site": _clean(row.get("site")),
                        "title": _clean(row.get("title")),
                        "company": _clean(row.get("company")),
                        "location": _clean(row.get("location")),
                        "is_remote": bool(row.get("is_remote"))
                        if row.get("is_remote") is not None and not pd.isna(row.get("is_remote"))
                        else False,
                        "url": url,
                        "description": _clean(row.get("description")),
                        "date_posted": _clean(row.get("date_posted")),
                        "search_term": term,
                        "role_family": family,
                    },
                )
                if inserted:
                    new_count += 1
            log.info("term %r (%s): %d results", term, family, len(jobs))

    return new_count
