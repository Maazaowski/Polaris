"""Profile edits that salt the fingerprint must trigger a template re-key."""

from polaris.fingerprint.fingerprinter import fingerprint_inputs_changed
from polaris.profiles.schema import LayoutFingerprintRules, SupplierProfile


def _profile(**overrides) -> SupplierProfile:
    base = {
        "profile_id": "acme.standard.v1",
        "identity": {"canonical_name": "Acme"},
    }
    base.update(overrides)
    return SupplierProfile.model_validate(base)


def test_cosmetic_edits_do_not_count(monkeypatch):
    import polaris.fingerprint.fingerprinter as fp

    monkeypatch.setattr(fp, "layout_fingerprint_config_from_profile", lambda p: ("cfg", p.classification.output_type))
    before = _profile()
    after = _profile(notes="Call Bob about the PO line")

    assert fingerprint_inputs_changed(before, after) is False

    rules = {"summary_anchors": ["Grand Total"]}
    assert fingerprint_inputs_changed(
        _profile(layout_fingerprint=rules), _profile(layout_fingerprint=rules, notes="cosmetic"),
    ) is False


def test_switching_between_legacy_and_profile_hash_counts():
    """No rules means the generic legacy hash; adding even empty rules switches
    to the profile-scoped hash, so the resolved config alone cannot tell."""
    assert fingerprint_inputs_changed(_profile(), _profile(layout_fingerprint={})) is True
    assert fingerprint_inputs_changed(_profile(layout_fingerprint={}), _profile()) is True


def test_fingerprint_rules_count_but_the_document_category_does_not(monkeypatch):
    """The category enters only the unused family key, never the hash, so a
    category edit leaves every model matching and must not re-key."""
    import polaris.fingerprint.fingerprinter as fp

    monkeypatch.setattr(
        fp, "layout_fingerprint_config_from_profile",
        lambda p: tuple((p.layout_fingerprint or LayoutFingerprintRules()).summary_anchors),
    )
    before = _profile()
    rules_changed = _profile(layout_fingerprint={"summary_anchors": ["Grand Total"]})
    category_changed = _profile(classification={"output_type": "wireless"})

    assert fingerprint_inputs_changed(before, rules_changed) is True
    assert fingerprint_inputs_changed(before, category_changed) is False
