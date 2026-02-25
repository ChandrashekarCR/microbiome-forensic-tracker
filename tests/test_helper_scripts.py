import pytest
import sys
import pandas as pd
from pathlib import Path

# Add workflow scripts to path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from workflow.scripts.helper_scripts import load_sample_sheet, get_sample_r1, get_sample_r2, get_sample_names

# Test the sample sheet in TSV file is loading properly
def test_load_sample_sheet(tmp_path):
    # Create a fake file to test
    
    (tmp_path / "a.fastq.gz").touch()
    (tmp_path / "b.fastq.gz").touch()
    (tmp_path / "c.fastq.gz").touch()
    (tmp_path / "d.fastq.gz").touch()

    tsv = tmp_path / "samples.tsv"

    tsv.write_text(
        f"sample\tr1\tr2\n"
        f"S1\t{tmp_path/'a.fastq.gz'}\t{tmp_path/'b.fastq.gz'}\n"
        f"S2\t{tmp_path/'c.fastq.gz'}\t{tmp_path/'d.fastq.gz'}\n"
    )

    df = load_sample_sheet(str(tsv))

    # Test if it is a valid sample sheet
    assert isinstance(df, pd.DataFrame)
    assert list(df.index) == ["S1","S2"]
    assert list(df.columns) == ["r1","r2"]

def test_missing_file():
    with pytest.raises(FileNotFoundError):
        load_sample_sheet("random.tsv")

# Test if there is a missing column
def test_missing_columns(tmp_path):
    tsv = tmp_path / "samples.tsv"

    tsv.write_text(
        "sample\tr1\n"
        "S1\ta.fastq.gz\n"
    )

    with pytest.raises(ValueError):
        load_sample_sheet(str(tsv))

# Test if the max samples parameter works
def test_max_samples(tmp_path):

    files = []
    for f in ["a","b","c","d","e","f"]:
        p = tmp_path / f"{f}.fastq.gz"
        p.touch()
        files.append(p)

    tsv = tmp_path / "samples.tsv"

    tsv.write_text(
        f"sample\tr1\tr2\n"
        f"S1\t{files[0]}\t{files[1]}\n"
        f"S2\t{files[2]}\t{files[3]}\n"
        f"S3\t{files[4]}\t{files[5]}\n"
    )

    df = load_sample_sheet(str(tsv), max_samples=2)

    assert len(df) == 2
    assert list(df.index) == ["S1", "S2"]