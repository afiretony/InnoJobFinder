import os

from jobfinder.config import PROJECT_ROOT, load_config

MATCH_PROMPT = os.path.join(PROJECT_ROOT, "prompts", "match.md")


def prompt_text():
    with open(MATCH_PROMPT) as f:
        return f.read()


def test_match_prompt_declares_its_placeholders():
    text = prompt_text()
    for token in ("{PROFILE}", "{CONSTRAINTS}", "{JOBS_JSON}"):
        assert token in text


def test_config_supplies_scoring_constraints():
    cfg = load_config()
    assert (cfg["matching"].get("constraints") or "").strip(), \
        "matching.constraints must be set; it is what makes scores yours"


def test_match_prompt_hardcodes_no_candidate_specifics():
    """The shared prompt must not bake in one person's background.

    Constraints belong in config.yaml. This guards against a personal profile
    creeping back into a file everyone who clones the repo inherits.
    """
    text = prompt_text().lower()
    for term in ("icra", "jetson", "tflite", "qnn", "uav", "ptq", "qat",
                 "software engineer ii", "4-person team", "on-device ai at scale"):
        assert term not in text, f"{term!r} leaked into the shared scoring prompt"


def test_match_prompt_forbids_prose_replies():
    """A template-looking profile once made the model ask for a real one instead of scoring."""
    assert "never reply with prose" in prompt_text().lower()
