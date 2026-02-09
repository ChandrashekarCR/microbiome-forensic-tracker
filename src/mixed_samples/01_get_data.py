
# Import libraries
import pandas as pd
import os
import argparse
from collections import Counter
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

# Create a mapper function to know the corresponding databases
def create_mapper(df):
    """
    Creates a mapper dictionary from the DataFrame.
    Key: fastqNames
    Value: List of dictionaries, each containing 'db' (database type) and 'batch' (batch number).
    Skips entries with empty or 'Fail' notes.
    """
    mapper = {}
    for _, row in df.iterrows():
        fastq = row['fastqNames']
        note = str(row['Notes_taxonomy']).strip()
        batch = row['Batch']
        if not note or 'Fail' in note:
            continue
        if 'core_nt' in note.lower():
            db = 'core_nt'
        elif 'standard' in note.lower():
            db = 'standard_db'
        else:
            continue
        if fastq not in mapper:
            mapper[fastq] = []
        mapper[fastq].append({'db': db, 'batch': batch})
    return mapper

# Function to load and process a single batch of csvs for a given level
def load_batch_data(batch_dir, level, mapper, base_dir):
    file_path = os.path.join(base_dir,f"{batch_dir}/short-read-taxonomy/final_reports/kraken_bracken_{level}.csv")
    if not os.path.exists(file_path):
        return pd.DataFrame() # Empty dataframe

    df = pd.read_csv(file_path).T.drop(['classifier','tax_id'],axis=0)
    df.columns = df.iloc[0]
    df = df.drop(df.index[0])
    df = df.reset_index(names='kobo_id')
    df.columns.name = 'sl.no'
    # Remove duplicate columns
    df = df.loc[:, ~df.columns.duplicated()] # Keeps the first occurance

    # Rename samples to include database (e.g., zr22822_105_core_nt_1)
    current_batch = int(batch_dir.split('batch')[-1])
    rename_dict = {}
    for sample in df['kobo_id']:
        if sample in mapper.keys():
            for entry in mapper[sample]:
                #if entry['db'] == 'core_nt': # If the entry is only from the core_nt database
                if entry['batch'] == current_batch: # If the batch is the same as current batch
                    new_name = f"{sample}_{entry['db']}_{current_batch}" # Change the name
                    rename_dict[sample] = new_name
                    break
    df['kobo_id'] = df['kobo_id'].map(rename_dict) # Rename the kobo_id to have the database name and the batch number as well
    df.index.name = None
    return df


# Merge all the batches according to their corresponding levels
# For example, merge all the batch of the same phylum, then same for the order and then for the class etc.

levels = ['phylum','class','order','family','genus','species']
def merge_batches(level, batch_dirs, mapper, base_dir):
    merged_data = {}
    # Skip batch3 and batch4 because they are results obtained from the standard database and not the core-nt
    for level in levels:
        print(f"\nMerging level: {level}")
        all_dfs = []
        for batch in batch_dirs:
            if batch in ['batch3','batch4']:
                continue
            df = load_batch_data(batch,level,mapper,base_dir)
            if not df.empty:
                # Set kobo_id as index for merging
                df = df.set_index('kobo_id')
                all_dfs.append(df)
                print(f"{batch}: {df.shape[0]} samples")

        if all_dfs:
            # Outer join on the columns taxa
            merged_df = pd.concat(all_dfs,axis=0,join='outer').fillna(0)
            merged_df = merged_df.infer_objects(copy=False)
            merged_df.index.name = "kobo_id"
            merged_df = merged_df.loc[:, (merged_df != 0).any(axis=0)]
            merged_data[level] = merged_df
            print(f"\nMerged {level}: {merged_df.shape[0]} samples, {merged_df.shape[1]} taxa")
        else:
            print(f"No data for {level}")       
    return merged_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge batch data for mixed samples.",
                                     usage="python3 01_get_data.py --base_dir <> --mapper <> --output_dir <>")
    parser.add_argument("--base_dir", type=str, required=True, help="Base directory containing batch folders")
    parser.add_argument("--mapper_file",type=str, required=True, help="Path to raw_data_table_batch.csv")
    parser.add_argument("--levels", nargs='+',default=['phylum','class','order','family','genus','species'],help="Taxonomic levels to merge.")
    parser.add_argument("--output_dir",type=str,default="01_merged_output", help="Directory to save the merged csvs.")

    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    # Read the mapper csv data
    df = pd.read_csv(args.mapper_file, sep='\t')
    mapper = create_mapper(df)
    #batch_dirs = [d for d in os.listdir(args.base_dir) if d.startswith('batch') and os.path.isdir(os.path.join(args.base_dir, d))]
    # Exclude batch3 and batch4 -> because they use Standard database instead of core-nt
    batch_dirs =['batch1','batch2','batch5','batch6','batch7','batch8','batch9','batch10','batch11','batch12','batch13','batch14']
    merged_data = merge_batches(args.levels,batch_dirs,mapper,args.base_dir)

    # Save them as individual csv files with respect to each taxonomy.
    for level, merged_df in merged_data.items():
        out_path = os.path.join(args.output_dir,f"merged_{level}.csv")
        merged_df.to_csv(out_path)
        print(f"Saved {level} data to {out_path}")

    print("Done!")


"python3 src/mixed_samples/01_get_data.py --base_dir /lunarc/nobackup/projects/snic2019-34-3/shared_elhaik_lab1/Projects/Microbiome/Results/Mixed2025_results --mapper_file data/mixed_samples/00_raw_data/raw_data_table_batch.csv --output_dir data/mixed_samples/01_merged_data/"