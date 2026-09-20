from custom_components.geodrops import transform as t


class Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_qcn_and_moisture_state_maps():
    assert t.qcn_to_state(2) == "Good"
    assert t.qcn_to_state(-1) == "Training"
    assert t.qcn_to_state(99) == "Unknown"
    assert t.moisture_index_to_state(0) == "Dry"
    assert t.moisture_index_to_state(5) == "Wet+"
    assert t.moisture_index_to_state(99) == "Unknown"


def test_classify_staleness_strict_gt():
    assert t.classify_staleness(5, 6, 12) == "ok"
    assert t.classify_staleness(6, 6, 12) == "ok"      # strict >
    assert t.classify_staleness(7, 6, 12) == "warn"
    assert t.classify_staleness(13, 6, 12) == "skip"


def test_reading_from_row_defaults_and_all_training():
    row = Row(deviceId=1001, moistureIndex=None, qcnDepth1=None,
              qcnDepth2=None, qcnDepth3=None)
    reading = t.reading_from_row(row)
    assert reading.device_id == 1001
    assert reading.moisture_index == -1     # _qcn default
    assert reading.moisture_pct == 0        # _num default
    assert t.all_training(reading) is True


def test_not_all_training_when_one_depth_known():
    row = Row(deviceId=1002, qcnDepth1=2, qcnDepth2=None, qcnDepth3=None)
    reading = t.reading_from_row(row)
    assert t.all_training(reading) is False
