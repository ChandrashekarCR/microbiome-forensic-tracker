import pytest
import sys
import pandas as pd
from pathlib import Path

# Add workflow scripts to path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from workflow.scripts.helper_scripts import read_sample_sheet, validate_sample_sheet, check_fastq_paths_exist, \
    load_sample_sheet, get_sample_r1, get_sample_r2, get_sample_names

@pytest.fixture
def valid_tsv_content():
    """Minimal valid TSV content for most tests."""
    # NOTE: Paths are intentionally relative; fixtures that need real files
    # must write absolute paths into the TSV (see valid_sample_df).
    return """sample\tr1\tr2
S1\ta.fastq.gz\tb.fastq.gz
S2\tc.fastq.gz\td.fastq.gz
"""


@pytest.fixture
def valid_sample_df(tmp_path, valid_tsv_content):
    """Fixture: A fully valid sample DataFrame (post-load_sample_sheet)."""
    files = ["a.fastq.gz", "b.fastq.gz", "c.fastq.gz", "d.fastq.gz"]
    for f in files:
        (tmp_path / f).touch()

    # Write absolute paths so check_fastq_paths_exist can find them
    tsv = tmp_path / "samples.tsv"
    tsv.write_text(
        f"sample\tr1\tr2\n"
        f"S1\t{tmp_path / 'a.fastq.gz'}\t{tmp_path / 'b.fastq.gz'}\n"
        f"S2\t{tmp_path / 'c.fastq.gz'}\t{tmp_path / 'd.fastq.gz'}\n"
    )

    return load_sample_sheet(str(tsv))


@pytest.fixture
def invalid_tsv_content():
    """Common invalid TSV patterns for error testing."""
    return [
        # missing TSV file (handled by read_sample_sheet)
        "",
        # missing columns
        "sample\tr1\nS1\ta.fastq.gz\n",
        "sample\tr2\nS1\tb.fastq.gz\n",
        # missing FASTQ files
        "sample\tr1\tr2\nS1\tmissing_r1.fastq.gz\tb.fastq.gz\n",
    ]


## 2. CORE TESTS: Each public function gets focused coverage
class TestLoadSampleSheet:
    """Tests for the main public function: load_sample_sheet()"""
    
    def test_happy_path_full_workflow(self, valid_sample_df):
        """End-to-end: valid TSV → valid DataFrame."""
        # Act + Assert
        assert isinstance(valid_sample_df, pd.DataFrame)
        assert len(valid_sample_df) == 2
        assert list(valid_sample_df.index) == ["S1", "S2"]
        assert list(valid_sample_df.columns) == ["r1", "r2"]
    
    def test_truncates_to_max_samples(self, tmp_path, valid_tsv_content):
        """max_samples limits output correctly."""
        files = ["a.fastq.gz", "b.fastq.gz", "c.fastq.gz", "d.fastq.gz"]
        for f in files:
            (tmp_path / f).touch()

        tsv = tmp_path / "samples.tsv"
        tsv.write_text(
            f"sample\tr1\tr2\n"
            f"S1\t{tmp_path / 'a.fastq.gz'}\t{tmp_path / 'b.fastq.gz'}\n"
            f"S2\t{tmp_path / 'c.fastq.gz'}\t{tmp_path / 'd.fastq.gz'}\n"
        )

        df = load_sample_sheet(str(tsv), max_samples=1)
        
        # Assert
        assert len(df) == 1
        assert list(df.index) == ["S1"]
    
    @pytest.mark.parametrize(
        "tsv_content, expected_error",
        [
            (None, FileNotFoundError),  # Non-existent file → FileNotFoundError
            ("sample\tr1\nS1\ta.fastq.gz\n", ValueError),  # Missing r2 column
            ("sample\tr2\nS1\tb.fastq.gz\n", ValueError),  # Missing r1 column
            ("sample\tr1\tr2\nS1\tmissing_r1.fastq.gz\tb.fastq.gz\n", FileNotFoundError),
        ],
        ids=["missing_file", "missing_r1_col", "missing_r2_col", "missing_fastq"]
    )
    def test_error_cases(self, tmp_path, tsv_content, expected_error):
        """Parametrized: covers multiple error paths with one test."""
        if tsv_content is None:
            # Use a path that doesn't exist at all
            with pytest.raises(expected_error):
                load_sample_sheet(str(tmp_path / "nonexistent.tsv"))
            return

        tsv = tmp_path / "samples.tsv"
        tsv.write_text(tsv_content)

        with pytest.raises(expected_error):
            load_sample_sheet(str(tsv))


class TestInternalHelpers:
    """Tests for internal functions (smaller scope)."""
    
    def test_read_sample_sheet_valid_file(self, tmp_path, valid_tsv_content):
        """read_sample_sheet loads TSV → DataFrame correctly."""
        tsv = tmp_path / "samples.tsv"
        tsv.write_text(valid_tsv_content)

        df = read_sample_sheet(str(tsv))
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2  # 2 data rows

    def test_read_sample_sheet_missing_file(self, tmp_path):
        """read_sample_sheet raises FileNotFoundError for missing TSV."""
        with pytest.raises(FileNotFoundError):
            read_sample_sheet(str(tmp_path / "missing.tsv"))
    
    def test_validate_sample_sheet_valid(self, tmp_path, valid_tsv_content):
        """validate_sample_sheet passes valid DataFrames through."""
        tsv = tmp_path / "samples.tsv"
        tsv.write_text(valid_tsv_content)
        df = read_sample_sheet(str(tsv))
        
        validated_df = validate_sample_sheet(df)
        assert len(validated_df) == 2  # Drops header row
    
    @pytest.mark.parametrize(
        "missing_col",
        ["r1", "r2"],
        ids=["missing_r1", "missing_r2"]
    )
    def test_validate_sample_sheet_missing_columns(self, tmp_path, missing_col):
        """validate_sample_sheet raises ValueError for missing columns."""
        content = f"sample\t{missing_col}\nS1\tsomepath.fastq.gz\n"
        tsv = tmp_path / "samples.tsv"
        tsv.write_text(content)
        df = read_sample_sheet(str(tsv))
        
        with pytest.raises(ValueError):
            validate_sample_sheet(df)
    
    def test_check_fastq_paths_exist_valid(self, valid_sample_df):
        """check_fastq_paths_exist passes when all files exist."""
        # No exception = success
        check_fastq_paths_exist(valid_sample_df)
    
    def test_check_fastq_paths_exist_missing_file(self, tmp_path, valid_tsv_content):
        """check_fastq_paths_exist raises FileNotFoundError for missing FASTQ."""
        files = ["a.fastq.gz", "b.fastq.gz", "c.fastq.gz", "d.fastq.gz"]
        for f in files:
            (tmp_path / f).touch()

        tsv = tmp_path / "samples.tsv"
        tsv.write_text(
            f"sample\tr1\tr2\n"
            f"S1\t{tmp_path / 'a.fastq.gz'}\t{tmp_path / 'b.fastq.gz'}\n"
            f"S2\t{tmp_path / 'c.fastq.gz'}\t{tmp_path / 'd.fastq.gz'}\n"
        )
        df = read_sample_sheet(str(tsv))
        df = validate_sample_sheet(df)

        (tmp_path / "a.fastq.gz").unlink()

        with pytest.raises(FileNotFoundError):
            check_fastq_paths_exist(df)


class TestSampleAccessors:
    """Tests for public accessor functions."""
    
    def test_get_sample_r1_valid(self, valid_sample_df):
        """get_sample_r1 returns correct R1 path."""
        r1_path = get_sample_r1(valid_sample_df, "S1")
        assert r1_path.endswith("a.fastq.gz")
    
    def test_get_sample_r2_valid(self, valid_sample_df):
        """get_sample_r2 returns correct R2 path."""
        r2_path = get_sample_r2(valid_sample_df, "S1")
        assert r2_path.endswith("b.fastq.gz")
    
    def test_get_sample_names_valid(self, valid_sample_df):
        """get_sample_names returns correct sample list."""
        samples = get_sample_names(valid_sample_df)
        assert samples == ["S1", "S2"]
    
    @pytest.mark.parametrize(
        "accessor_func, sample_id",
        [
            (get_sample_r1, "S1"),
            (get_sample_r2, "S1")
        ],
        ids=["get_r1", "get_r2"]
    )
    def test_accessor_error_on_missing_sample(self, valid_sample_df, accessor_func, sample_id):
        """Accessors handle missing samples gracefully (KeyError)."""
     
        with pytest.raises(KeyError):
            accessor_func(valid_sample_df, "missing_sample")


# INtegration test - full workflow edge cases
def test_integration_empty_rows_handled(tmp_path):
    """Integration: validate_sample_sheet drops empty rows correctly."""
    files = ["a.fastq.gz", "b.fastq.gz", "c.fastq.gz", "d.fastq.gz"]
    for f in files:
        (tmp_path / f).touch()

    tsv = tmp_path / "samples.tsv"
    tsv.write_text(
        f"sample\tr1\tr2\n"
        f"S1\t{tmp_path / 'a.fastq.gz'}\t{tmp_path / 'b.fastq.gz'}\n"
        f"S2\t\t\n"
        f"S3\t{tmp_path / 'c.fastq.gz'}\t{tmp_path / 'd.fastq.gz'}\n"
    )

    df = load_sample_sheet(str(tsv))
    assert len(df) == 2  # S1 and S3 only
    assert list(df.index) == ["S1", "S3"]
