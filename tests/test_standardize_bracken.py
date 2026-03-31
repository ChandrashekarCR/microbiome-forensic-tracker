"""
Unit tests for standardize_bracken.py
These tests validate the Bracken output processing functions.
"""

import pandas as pd
import pytest

from smk_helper.standardize_bracken import concat_tables, standardize_bracken


class TestStandardizeBracken:
    """Tests for standardize_bracken function."""

    @pytest.fixture
    def sample_bracken_output(self, tmp_path):
        sample_dir = tmp_path / "sample1"
        sample_dir.mkdir()

        bracken_content = """name\ttaxonomy_id\ttaxonomy_lvl\tkraken_assigned_reads\tadded_reads\tnew_est_reads\tfraction_total_reads
Escherichia coli\t562\tS\t1000\t100\t1100\t0.012
Salmonella enterica\t28901\tS\t500\t50\t550\t0.006
Staphylococcus aureus\t1280\tS\t50\t5\t55\t0.0006
"""
        input_file = sample_dir / "species.bracken"
        input_file.write_text(bracken_content)
        return str(input_file)

    def test_standardize_bracken_basic(self, sample_bracken_output, tmp_path):
        """
        Test basic Bracken standardization.

        What we're testing:
        - Function reads Bracken output correctly
        - Applies minimum abundance filter
        - Creates standardized output format
        - Saves output file
        """
        output_dir = tmp_path / "standardized"
        output_dir.mkdir()

        standardize_bracken(
            sample_bracken_output, output_dir=str(output_dir), min_abd=0.001
        )

        # Check output file was created
        expected_file = output_dir / "sample1_species.csv"
        assert expected_file.exists(), "Output file should be created"

        # Verify output content
        df = pd.read_csv(expected_file)

        # Check column names are standardized
        assert list(df.columns) == ["classifier", "clade", "tax_id", "sample1"]

        # Check classifier column
        assert all(df["classifier"] == "kraken_bracken")

        # Check abundance filtering works
        # E. coli (0.012) and S. enterica (0.006) should pass threshold
        # S. aureus (0.0006) should be set to 0
        assert df[df["clade"] == "Escherichia coli"]["sample1"].values[0] > 0
        assert df[df["clade"] == "Salmonella enterica"]["sample1"].values[0] > 0
        assert df[df["clade"] == "Staphylococcus aureus"]["sample1"].values[0] == 0

    def test_standardize_bracken_threshold(self, tmp_path):
        """
        Test abundance threshold filtering.

        What we're testing:
        - min_abd parameter correctly filters low-abundance taxa
        """
        # Create test Bracken file
        sample_dir = tmp_path / "test_sample"
        sample_dir.mkdir()

        bracken_content = """name\ttaxonomy_id\ttaxonomy_lvl\tkraken_assigned_reads\tadded_reads\tnew_est_reads\tfraction_total_reads
High_abundance\t1\tS\t10000\t1000\t11000\t0.1
Medium_abundance\t2\tS\t500\t50\t550\t0.005
Low_abundance\t3\tS\t10\t1\t11\t0.0001
"""
        input_file = sample_dir / "species.bracken"
        input_file.write_text(bracken_content)

        output_dir = tmp_path / "out"
        output_dir.mkdir()

        # Test with threshold of 0.001
        standardize_bracken(str(input_file), output_dir=str(output_dir), min_abd=0.001)

        df = pd.read_csv(output_dir / "test_sample_species.csv")

        # High and medium should pass, low should be filtered
        assert df[df["clade"] == "High_abundance"]["test_sample"].values[0] == 0.1
        assert df[df["clade"] == "Medium_abundance"]["test_sample"].values[0] == 0.005
        assert df[df["clade"] == "Low_abundance"]["test_sample"].values[0] == 0


class TestConcatTables:
    """Tests for concat_tables function."""

    def test_concat_tables_single_file(self, tmp_path):
        """
        Test concatenation with single input file.

        What we're testing:
        - Single file is simply copied to output
        """
        input_dir = tmp_path / "inputs"
        input_dir.mkdir()

        # Create single standardized file
        df = pd.DataFrame(
            {
                "classifier": ["kraken_bracken", "kraken_bracken"],
                "clade": ["Taxon1", "Taxon2"],
                "tax_id": [123, 456],
                "sample1": [0.5, 0.3],
            }
        )

        input_file = input_dir / "sample1_species.csv"
        df.to_csv(input_file, index=False)

        output_file = tmp_path / "merged.csv"

        concat_tables([str(input_file)], str(output_file))

        # Verify output matches input
        assert output_file.exists()
        result_df = pd.read_csv(output_file)
        pd.testing.assert_frame_equal(df, result_df)

    def test_concat_tables_multiple_files(self, tmp_path):
        """
        Test merging multiple sample files.

        What we're testing:
        - Multiple samples are merged correctly
        - Outer join includes all taxa from all samples
        - Missing values are filled with 0
        """
        input_dir = tmp_path / "inputs"
        input_dir.mkdir()

        # Create sample 1
        df1 = pd.DataFrame(
            {
                "classifier": ["kraken_bracken", "kraken_bracken"],
                "clade": ["E. coli", "S. aureus"],
                "tax_id": ["562", "1280"],
                "sample1": [0.5, 0.3],
            }
        )
        file1 = input_dir / "sample1_species.csv"
        df1.to_csv(file1, index=False)

        # Create sample 2 (different taxa)
        df2 = pd.DataFrame(
            {
                "classifier": ["kraken_bracken", "kraken_bracken"],
                "clade": ["E. coli", "B. subtilis"],
                "tax_id": ["562", "1423"],
                "sample2": [0.4, 0.2],
            }
        )
        file2 = input_dir / "sample2_species.csv"
        df2.to_csv(file2, index=False)

        output_file = tmp_path / "merged.csv"

        concat_tables([str(file1), str(file2)], str(output_file))

        # Verify merged output
        result_df = pd.read_csv(output_file)

        # Should have 3 unique taxa
        assert len(result_df) == 3

        # Check column structure
        assert "classifier" in result_df.columns
        assert "clade" in result_df.columns
        assert "tax_id" in result_df.columns
        assert "sample1" in result_df.columns
        assert "sample2" in result_df.columns

        # Check E. coli present in both samples
        ecoli = result_df[result_df["clade"] == "E. coli"]
        assert ecoli["sample1"].values[0] == 0.5
        assert ecoli["sample2"].values[0] == 0.4

        # Check S. aureus only in sample1 (sample2 should be 0)
        saureus = result_df[result_df["clade"] == "S. aureus"]
        assert saureus["sample1"].values[0] == 0.3
        assert saureus["sample2"].values[0] == 0

        # Check B. subtilis only in sample2 (sample1 should be 0)
        bsubtilis = result_df[result_df["clade"] == "B. subtilis"]
        assert bsubtilis["sample1"].values[0] == 0
        assert bsubtilis["sample2"].values[0] == 0.2

    def test_concat_tables_duplicate_taxa(self, tmp_path):
        """
        Test handling of duplicate taxa within same file.

        What we're testing:
        - Duplicates are summed correctly
        """
        input_dir = tmp_path / "inputs"
        input_dir.mkdir()

        # Create file with duplicate taxa
        df = pd.DataFrame(
            {
                "classifier": ["kraken_bracken", "kraken_bracken", "kraken_bracken"],
                "clade": ["E. coli", "E. coli", "S. aureus"],
                "tax_id": [562, 562, 1280],
                "sample1": [0.3, 0.2, 0.1],  # Two E. coli entries
            }
        )

        input_file = input_dir / "sample1_species.csv"
        df.to_csv(input_file, index=False)

        # Create second file to trigger the actual merge logic in concat_tables
        df2 = pd.DataFrame(
            {
                "classifier": ["kraken_bracken"],
                "clade": ["B. subtilis"],
                "tax_id": [1423],
                "sample2": [0.5],
            }
        )

        input_file2 = input_dir / "sample2_species.csv"
        df2.to_csv(input_file2, index=False)

        output_file = tmp_path / "merged.csv"

        concat_tables([str(input_file), str(input_file2)], str(output_file))

        result_df = pd.read_csv(output_file)

        # Should have 3 unique taxa in total
        assert len(result_df) == 3

        # E. coli values should be summed
        ecoli = result_df[result_df["clade"] == "E. coli"]
        assert ecoli["sample1"].values[0] == 0.5  # 0.3 + 0.2
