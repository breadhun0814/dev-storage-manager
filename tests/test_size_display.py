import pytest
from dev_storage_manager.ui.formatting import format_size, exact_size


@pytest.mark.parametrize("value, expected", [(0, "0 B"), (1023, "1,023 B"),
    (1024, "1.0 KB"), (1536, "1.5 KB"), (1024**2, "1.0 MB"),
    (1024**3, "1.0 GB"), (1024**4, "1.0 TB"), (-1024**2, "−1.0 MB")])
def test_automatic_units(value, expected):
    assert format_size(value) == expected


def test_exact_byte_tooltip_preserves_precision():
    assert "1,048,577 B" in exact_size(1048577)
