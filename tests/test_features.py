import pandas as pd
import pytest

from src.ml.features import ZeroColumnFilter


@pytest.mark.parametrize(
    "min_prevalence, X, expected_cols",
    [
        (
            0.05,
            pd.DataFrame(
                {
                    "a": [0, 0, 0, 0],
                    "b": [1, 0, 0, 0],
                    "c": [1, 1, 1, 1],
                }
            ),
            ["c"],
        ),
        (
            0.25,
            pd.DataFrame(
                {
                    "a": [0, 0, 1, 0],  # prevalence 0.25
                    "b": [1, 0, 0, 0],  # prevalence 0.25
                    "c": [1, 1, 1, 1],  # prevalence 1.0
                }
            ),
            ["a", "b", "c"],
        ),
        (
            0.5,
            pd.DataFrame(
                {
                    "a": [0, 0, 1, 0],  # prevalence 0.25
                    "b": [1, 0, 0, 0],  # prevalence 0.25
                    "c": [1, 1, 1, 1],  # prevalence 1.0
                }
            ),
            ["c"],
        ),
    ],
)
def test_zero_column_filter(min_prevalence, X, expected_cols):
    filt = ZeroColumnFilter(min_prevalence=min_prevalence)
    filt.fit(X)

    assert filt.keep_cols_ == expected_cols

    Xt = filt.transform(X)
    assert list(Xt.columns) == expected_cols
    assert all(dtype == "float64" for dtype in Xt.dtypes)
