# Import libraries
import os
import shutil

import pandas as pd


def standardize_bracken(input_file: str, output_dir=None, min_abd: float = 0.001):
    df = pd.read_csv(input_file, sep="\t")
    abs_path = input_file.split("/")  # This works only if the file format follows the pipeline conventions
    sample = abs_path[-2]
    rank = abs_path[-1].split(".")[0]
    df["classifier"] = "kraken_bracken"

    # Set abundance to zero if below the threshold
    df[sample] = df.apply(
        lambda row: row["fraction_total_reads"] if row["fraction_total_reads"] >= min_abd else 0,
        axis=1,
    )

    standardized_df = df[["classifier", "name", "taxonomy_id", sample]]
    standardized_df.columns = ["classifier", "clade", "tax_id", sample]

    standardized_df.to_csv(os.path.join(output_dir, sample + "_" + rank + ".csv"), header=True, index=False)


def concat_tables(sample_list, fo):
    if len(sample_list) == 1:
        shutil.copy(sample_list[0], fo)
        return

    merged = None
    sample_cols = []

    for path in sample_list:
        df = pd.read_csv(path, header=0)

        # The last column contains the sample names
        sample = df.columns[-1]
        sample_cols.append(sample)

        # Normalize key fields to avoid mismaticsa due to extra spaces
        df["classifier"] = df["classifier"].astype(str).str.strip()
        df["clade"] = df["clade"].astype(str).str.strip()
        df["tax_id"] = df["tax_id"].astype(str).str.strip()

        # Keep only the relevant columns
        df = df[["classifier", "clade", "tax_id", sample]]

        # If there are duplicate taxa within the same file then sum their values
        df = df.groupby(["classifier", "clade", "tax_id"], as_index=False).sum(numeric_only=True)

        # For the first file, initialize the merged table; for the next files perfrom an outer merge on taxonomic keys
        if merged is None:
            merged = df
        else:
            merged = pd.merge(merged, df, on=["classifier", "clade", "tax_id"], how="outer")

        # Replace any missising abundance values with - for each sample column
        for col in sample_cols:
            if col in merged.columns:
                merged[col] = merged[col].fillna(0)

        # Save the merged table
        merged.to_csv(fo, header=True, index=False)
