import pytest
import sys
from pathlib import Path

# Add workflow scripts to path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from workflow.scripts.generate_sample_sheet import generate_sample_sheet

# Test that TSV is created correctly from fake FASTQ files
def test_generate_sample_sheet_basic(tmp_path):

    # Create fake fastq files
    data_dir = tmp_path / "fastqs"
    data_dir.mkdir()

    (data_dir / "S1_R1.fastq.gz").touch()
    (data_dir / "S1_R2.fastq.gz").touch()
    (data_dir / "S2_R1.fastq.gz").touch()
    (data_dir / "S2_R2.fastq.gz").touch()

    # Output file
    output = tmp_path / "samples.tsv"

    # Run the function
    generate_sample_sheet(str(data_dir),str(output))

    # Assertions
    # Cheeck if the output exists
    assert output.exists()

    content = output.read_text().strip().splitlines()

    # Header
    assert content[0] == "sample\tr1\tr2"

    # Rows (order sorted)
    assert "S1\t" in content[1]
    assert "S2\t" in content[2]

    # Check if the file paths exists in the output
    for line in content[1:]:
        sample, r1, r2 = line.split("\t")
        assert Path(r1).exists()
        assert Path(r2).exists()

def test_missing_r2_raises_error(tmp_path):
    data_dir = tmp_path / "fastqs"
    data_dir.mkdir()

    (data_dir / "S1_R1.fastq.gz").touch()

    # Raise an error if there is only one read present
    with pytest.raises(FileNotFoundError):
        generate_sample_sheet(str(data_dir), str(tmp_path / "out.tsv"))