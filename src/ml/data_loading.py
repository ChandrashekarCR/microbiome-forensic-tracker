# Importing libraries
import argparse
import sqlite3
import json

import pandas as pd
import numpy as np
import io
import os 
import glob

from malmo_samples import db_reader


class DatabaseRSA:
    def __init__(self, db, db_table):
        self.db = db
        self.db_table = db_table

    def connect_to_database(self) -> pd.DataFrame:

        # Connect to database
        conn = sqlite3.connect(self.db)

        query = f"""
                SELECT * FROM {self.db_table};
                """

        df = pd.read_sql_query(query, conn)

        conn.close()

        return df

    def format_data(self, df: pd.DataFrame) -> pd.DataFrame:

        # Drop the classifier column
        df = df.drop(columns=["classifier", "tax_id"])
        df = df.rename(columns={"clade": "sample_id"})
        df = df.set_index("sample_id")

        # Reshape the dataframe
        df = df.T

        df = df.reset_index()
        df = df.rename(columns={"index": "sample_id"})
        return df

    def merge_data(self, metadata_df: pd.DataFrame, rsa_df: pd.DataFrame) -> pd.DataFrame:

        # Merge the data
        df = pd.merge(metadata_df, rsa_df, on="sample_id", how="inner")

        # Drop columns
        df = df.drop(columns=["barcode", "name", "date", "time", "altitude", "precision"],axis=1)

        # 1. Enforce string datatypes
        df['sample_id'] = df['sample_id'].astype(str)
        df['zone'] = df['zone'].astype(str)
        
        # 2. Enforce float for coordinates
        df['latitude'] = df['latitude'].astype(float)
        df['longitude'] = df['longitude'].astype(float)
        
        # 3. Enforce float for all remaining abundance columns
        taxa_cols = [col for col in df.columns if col not in ['sample_id', 'zone', 'latitude', 'longitude']]
        df[taxa_cols] = df[taxa_cols].astype(float)

        return df

    def sql_to_clean(self) -> pd.DataFrame:
        """
        Return a complete dataframe for ML
        """
        df = self.connect_to_database()
        df = self.format_data(df)
        return df


class DatabaseDNABERTS:
    def __init__(self, db_path:str):
        self.db_path = db_path
    
    def create_table(self):
        """
        Create the embeddings table if it does not exist
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
               CREATE TABLE IF NOT EXISTS embeddings (
                    sample_id TEXT PRIMARY KEY,
                    num_contigs INTEGER NOT NULL CHECK (num_contigs >= 0),
                    embeddings BLOB NOT NULL
               )         
            """
        )

        conn.commit()
        conn.close()

    def insert_from_json(self, sample_id: str, json_path:str):
        """
        Reads the json file and convert the embeddings into numpy array and stores as BLOB (Binary Large Object)
        """
        with open(json_path,'r') as f:
            data = json.load(f)

        # 1. Convert from list to numpy array 
        emb_array = np.array(data['embeddings'],dtype=np.float32)
        num_contigs = len(data.get('contig_ids',[]))

        # 2. Serialize numpy array into bytes
        out = io.BytesIO()
        np.save(out, emb_array)
        serialized_array = out.getvalue()

        # 3. Insert into SQLite Database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO embeddings (sample_id, num_contigs, embeddings)
            VALUES (?, ?, ?)
            """,
            (sample_id,num_contigs,serialized_array)
        )
        conn.commit()
        conn.close()

    def get_embeddings(self,sample_id:str) -> np.ndarray:
        """
        Retrieve and reconstruct the numpy array from BLOB
        """

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT embeddings from embeddings WHERE sample_id = ?
            """,
            (sample_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None
        
        # Reconstruct numpy array from bytes
        in_buffer = io.BytesIO(row[0])
        emb_array = np.load(in_buffer)

        return emb_array
    
    def load_data_(self,base_dir:str):

        # Create the table
        self.create_table()

        # Find all the json files matching the pattern
        search_pattern = os.path.join(base_dir,"zr*","*_embeddings.json")
        json_files = glob.glob(search_pattern)

        print(f"Found {len(json_files)} JSON files. Starting import...")

        for file_path in json_files:
            filename = os.path.basename(file_path)
            sample_id = filename.replace("_embeddings.json","")

            try:
                self.insert_from_json(sample_id,file_path)
                print(f"Loaded: {sample_id}")
            except Exception as e:
                print(f"Failed to load {sample_id}: {e}")
        
        print(f"Finished loading all the embeddings into database")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A script to get the data from the database.", usage="")
    parser.add_argument("-i", dest="database", required=True, help="Enter the path to the database.")
    parser.add_argument("-t", dest="table", required=False, help="Enter the RSA table.")
    parser.add_argument("-b", dest="bert_dir",required=False, help="Enter the path to the DNABERT-S JSON file")
    args = parser.parse_args()

    samples = db_reader.DatabaseCreate(db=args.database)
    #print(samples.get_samples())
#
    rsa = DatabaseRSA(db=args.database, db_table=args.table)
    #print(rsa.sql_to_clean())
#
    #df = rsa.merge_data(samples.get_samples(), rsa.sql_to_clean())
    #print(df)

    db_bert = DatabaseDNABERTS(args.database)
    db_bert.load_data_(args.bert_dir)
