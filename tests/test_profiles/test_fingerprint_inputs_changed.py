"""Profile edits that salt the fingerprint must trigger a template re-key."""

from polaris.api.profiles import fingerprint_inputs_changed
from polaris.profiles.schema import LayoutFingerprintRules, SupplierProfile


def _profile(**overrides) -> SupplierProfile:
    base = {
        "profile_id": "acme.standard.v1",
        "identity": {"canonical_name": "Acme"},
        "output_spec_id": "temforce.standard",
        "field_schema_id": "invoice.standard",
    }
    base.update(overrides)
    return SupplierProfile.model_validate(base)


def test_cosmetic_edits_do_not_count(monkeypatch):
    import polaris.fingerprint.fingerprinter as fp

    monkeypatch.setattr(fp, "layout_fingerprint_config_from_profile", lambda p: ("cfg", p.classification.output_type))
    before = _profile()
    after = _profile(notes="Call Bob about the PO line")

    assert fingerprint_inputs_changed(before, after) is False


def test_fingerprint_rules_and_category_count(monkeypatch):
    import polaris.fingerprint.fingerprinter as fp

    monkeypatch.setattr(
        fp, "layout_fingerprint_config_from_profile",
        lambda p: tuple((p.layout_fingerprint or LayoutFingerprintRules()).summary_anchors),
    )
    before = _profile()
    rules_changed = _profile(layout_fingerprint={"summary_anchors": ["Grand Total"]})
    category_changed = _profile(classification={"output_type": "wireless"})

    assert fingerprint_inputs_changed(before, rules_changed) is True
    assert fingerprint_inputs_changed(before, category_changed) is True
