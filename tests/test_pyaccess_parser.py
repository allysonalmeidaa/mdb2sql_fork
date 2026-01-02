import decimal

import pytest

from convert_pyaccess_parser import _infer_column_type, _normalize_cell


def test_infer_column_type_numeric_mixed():
    values = [1, 2.5, 3]
    assert _infer_column_type(values) == "DOUBLE"


def test_infer_column_type_decimal():
    values = [decimal.Decimal("12.34"), decimal.Decimal("0.1")]
    assert _infer_column_type(values) == "DECIMAL(38,10)"


def test_infer_column_type_string_mixed_numeric():
    values = ["1", 2]
    assert _infer_column_type(values) == "VARCHAR"


def test_normalize_cell_decimal_and_bool():
    assert _normalize_cell(decimal.Decimal("1.23"), "DECIMAL(38,10)") == decimal.Decimal(
        "1.23"
    )
    assert _normalize_cell(True, "BIGINT") == 1


def test_normalize_cell_blob():
    assert _normalize_cell(b"abc", "BLOB") == b"abc"


@pytest.mark.parametrize(
    "value,target",
    [
        (None, "VARCHAR"),
        ("text", "VARCHAR"),
    ],
)
def test_normalize_cell_passthrough(value, target):
    assert _normalize_cell(value, target) == value
