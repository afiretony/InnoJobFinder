from jobfinder import generic_cv as g


class FakeRow(dict):
    def __getitem__(self, k):
        return dict.__getitem__(self, k)


SEEDS = [FakeRow(id="a1", title="AI Engineer", company="Acme", description="Build agents.")]


def cfg_with(name="Jordan Doe", deemph=None):
    cfg = {"candidate": {"name": name}, "tailoring": {}}
    if deemph is not None:
        cfg["tailoring"]["deemphasize_project"] = deemph
    return cfg


def render(category, cfg=None):
    return g.render_prompt(cfg or cfg_with(), category, SEEDS, "/tmp/out", "2026-07-10")


def test_deemphasize_excludes_named_project_from_listed_categories():
    cfg = cfg_with(deemph={"name": "My Startup", "exclude_categories": ["general_swe", "fullstack_product"]})
    for category in ("general_swe", "fullstack_product"):
        assert "Do not include the My Startup project" in render(category, cfg)


def test_deemphasize_keeps_project_for_unlisted_category():
    cfg = cfg_with(deemph={"name": "My Startup", "exclude_categories": ["general_swe"]})
    assert "Do not include" not in render("ai_llm_engineer", cfg)


def test_no_deemphasize_configured_keeps_everything():
    assert "Do not include" not in render("general_swe", cfg_with())


def test_no_placeholders_survive_rendering():
    prompt = render("ml_research")
    for token in ("{CATEGORY}", "{CATEGORY_BLURB}", "{SEED_JOBS}", "{OUT_DIR}",
                  "{PDF_NAME}", "{TEX_NAME}", "{DATE}", "{CATEGORY_RULES}"):
        assert token not in prompt


def test_prompt_carries_category_and_seed_jobs():
    prompt = render("inference_optimization")
    assert "inference_optimization" in prompt
    assert "AI Engineer @ Acme" in prompt
    assert "Build agents." in prompt


def test_cv_filename_uses_candidate_name():
    prompt = render("ml_research", cfg_with(name="Jordan Doe"))
    assert "Jordan_Doe_CV_ml_research.pdf" in prompt
    assert "Jordan_Doe_CV_ml_research.tex" in prompt


def test_cv_prefix_falls_back_when_no_name():
    assert g.cv_prefix({"candidate": {"name": ""}}) == "CV"
    assert g.cv_prefix({}) == "CV"
    assert g.cv_prefix({"candidate": {"name": "Ada Lovelace"}}) == "Ada_Lovelace_CV"


def test_cv_status_missing_when_no_pdf(tmp_path):
    cfg = {"paths": {"output_dir": str(tmp_path), "profile": str(tmp_path / "p.md")}}
    (tmp_path / "p.md").write_text("profile")
    assert g.cv_status(cfg, "general_swe") == "missing"


def test_cv_status_stale_when_profile_changes(tmp_path):
    profile = tmp_path / "p.md"
    profile.write_text("original")
    cfg = {"paths": {"output_dir": str(tmp_path), "profile": str(profile)}}
    d = tmp_path / "generic" / "general_swe"
    d.mkdir(parents=True)
    (d / "CV_general_swe.pdf").write_bytes(b"%PDF")
    (d / "meta.json").write_text('{"profile_sha": "%s"}' % g.profile_sha(cfg))
    assert g.cv_status(cfg, "general_swe") == "current"

    profile.write_text("edited")
    assert g.cv_status(cfg, "general_swe") == "stale"
