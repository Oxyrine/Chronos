import pytest

from chronos.common import samples

KINDS = ["cbom_component", "finding", "shelflife_prediction", "exposure", "patch_proposal", "verification_result",
         "attestation", "tls_event", "anomaly_alert", "topology", "ground_truth", "client_mix", "metrics"]


@pytest.mark.parametrize("kind", KINDS)
def test_sample_validates(kind):
    samples.validate(kind, samples.sample(kind))


def test_bad_enum_rejected():
    import jsonschema
    bad = {**samples.sample("finding"), "quantum_status": "kinda"}
    with pytest.raises(jsonschema.ValidationError):
        samples.validate("finding", bad)


def test_requires_human_must_be_true():
    import jsonschema
    bad = {**samples.sample("patch_proposal"), "requires_human": False}
    with pytest.raises(jsonschema.ValidationError):
        samples.validate("patch_proposal", bad)
