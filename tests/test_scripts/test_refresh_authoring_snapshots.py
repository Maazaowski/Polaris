"""scripts/refresh_authoring_snapshots.py with the AI calls stubbed out.

The "AI" ground truth is the committed euNetworks model's own output and the
"authored" model is that committed model (or the Colt one, to force a failure),
so the grounded loop, the generalization check and the write/no-write decision
all run for real without a key. The layout is a copy under tmp_path, so the
committed snapshot is never touched.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

from polaris import runtime_settings
from polaris.config import settings
from polaris.llm.config import default_model
from polaris.profiles import loader as profiles_loader
from tests.corpus_utils import CORPUS_ROOT, CorpusLayout

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "refresh_authoring_snapshots.py"
LAYOUT = "eunetworks.standard"
SENTINEL = '{"sentinel": true}\n'


def _load_script():
    spec = importlib.util.spec_from_file_location("refresh_authoring_snapshots", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Dataclasses with postponed annotations resolve them through sys.modules.
    sys.modules["refresh_authoring_snapshots"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def script(tmp_path, monkeypatch):
    """The script module, its layout discovery pointed at a tmp copy of the corpus layout."""
    module = _load_script()
    root = tmp_path / "corpus" / LAYOUT
    shutil.copytree(CORPUS_ROOT / LAYOUT, root)
    committed = CorpusLayout(LAYOUT, root, sorted((root / "invoices").glob("*.pdf"))).load_model()
    (root / "model.json").write_text(SENTINEL, encoding="utf-8")
    layout = CorpusLayout(LAYOUT, root, sorted((root / "invoices").glob("*.pdf")))
    monkeypatch.setattr(module, "discover_layouts", lambda: [layout])

    # main() repoints the operational dirs; restore them after the test.
    for attr in ("work_dir", "inbound_dir", "processing_dir", "completed_dir", "exceptions_dir",
                 "archive_dir", "extraction_models_dir"):
        monkeypatch.setattr(settings, attr, getattr(settings, attr))
    monkeypatch.setattr(settings, "model_authoring_max_attempts", 2)
    # Provider preflight: an env key for the default provider, nothing stored, fresh runtime cache.
    for attr, value in (("llm_provider", "openai"), ("openai_api_key", "test-key"), ("anthropic_api_key", ""),
                        ("secret_key", ""), ("openai_model_extraction", "gpt-5.5"),
                        ("openai_model_model_generation", "gpt-5.5")):
        monkeypatch.setattr(settings, attr, value)
    monkeypatch.setattr(runtime_settings, "_cache", None)
    # A saved runtime-settings row (other tests write one) would beat the env values.
    monkeypatch.setattr("polaris.db.registry.get_runtime_setting", lambda db, key: None)

    profile = layout.load_profile()
    calls = {"extract": 0, "author": 0}

    def fake_extract(pdf, *, supplier_profile_id, **kwargs):
        calls["extract"] += 1
        # The registry has no such row; the script serves the committed fixture profile.
        for get_profile in (profiles_loader.get_profile, module.extractor.get_profile):
            served = get_profile(supplier_profile_id)
            assert served is not None and served.profile_id == profile.profile_id
        return type("Extraction", (), {"raw_data": {}})()

    def fake_canonical(*, intake_id, **kwargs):
        return module.execute_model(committed, layout.pdfs[0], intake_id)

    authored = {"model": committed}

    def fake_author(**kwargs):
        calls["author"] += 1
        return type("Auth", (), {"model": authored["model"]})()

    monkeypatch.setattr(module, "extract_invoice", fake_extract)
    monkeypatch.setattr(module, "build_canonical_invoice", fake_canonical)
    monkeypatch.setattr(module, "author_extraction_model", fake_author)
    module.calls = calls
    module.authored = authored
    module.layout = layout
    return module


def test_dry_run_authors_but_does_not_write(script, tmp_path):
    assert script.main(["--dry-run", "--work-dir", str(tmp_path / "work")]) == 0

    assert script.calls == {"extract": 1, "author": 1}
    assert script.layout.model_path.read_text(encoding="utf-8") == SENTINEL
    assert settings.work_dir == (tmp_path / "work").resolve()


def test_reproducing_layout_writes_the_snapshot(script, tmp_path):
    assert script.main(["--only", LAYOUT, "--work-dir", str(tmp_path / "work")]) == 0

    written = script.layout.load_model()
    assert written.model_dump(mode="json") == script.authored["model"].model_dump(mode="json")


def test_failing_layout_exits_non_zero_and_keeps_the_snapshot(script, tmp_path):
    # Colt's rules cannot reproduce a euNetworks invoice, so the loop never converges.
    script.authored["model"] = CorpusLayout("colt.standard", CORPUS_ROOT / "colt.standard").load_model()

    assert script.main(["--work-dir", str(tmp_path / "work")]) == 1

    assert script.calls["author"] == 2  # re-authored up to model_authoring_max_attempts
    assert script.layout.model_path.read_text(encoding="utf-8") == SENTINEL
    # The loader patch is undone after each layout.
    assert script.profiles_loader.get_profile is profiles_loader.get_profile
    assert script.extractor.get_profile is profiles_loader.get_profile


def test_missing_provider_key_stops_before_any_ai_call(script, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")

    assert script.main(["--work-dir", str(tmp_path / "work")]) == 2
    assert script.calls == {"extract": 0, "author": 0}


def test_anthropic_from_env_swaps_the_openai_default_models(script, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")

    assert script.main(["--dry-run", "--work-dir", str(tmp_path / "work")]) == 0
    assert runtime_settings.openai_model_extraction() == default_model("anthropic")
    assert runtime_settings.openai_model_model_generation() == default_model("anthropic")


def test_unknown_layout_is_rejected(script, tmp_path):
    assert script.main(["--only", "nope.standard", "--work-dir", str(tmp_path / "work")]) == 2
    assert script.calls == {"extract": 0, "author": 0}
