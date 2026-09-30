import pandas as pd

from mednexus.ml.readmission import patient_disjoint_split


def test_patient_split_has_no_patient_leakage():
    rows = []
    for patient in range(20):
        rows.extend(
            [
                {"subject_id": patient, "readmitted_30d": patient % 2},
                {"subject_id": patient, "readmitted_30d": 0},
            ]
        )
    frame = pd.DataFrame(rows)

    train, validation, test = patient_disjoint_split(frame)

    train_ids = set(train["subject_id"])
    validation_ids = set(validation["subject_id"])
    test_ids = set(test["subject_id"])
    assert train_ids.isdisjoint(validation_ids)
    assert train_ids.isdisjoint(test_ids)
    assert validation_ids.isdisjoint(test_ids)
    assert train_ids | validation_ids | test_ids == set(frame["subject_id"])
