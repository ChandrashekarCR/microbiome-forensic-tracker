# Importing libraries
import argparse
import sqlite3

import pandas as pd
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
        df = df.drop(columns=['classifier','tax_id'],axis=1)
        df = df.rename(columns={'clade':'sample_id'})
        df = df.set_index('sample_id')

        # Reshape the dataframe
        df = df.T

        df = df.reset_index()
        df = df.rename(columns={'index': 'sample_id'})
        return df
    
    def merge_data(self, metadata_df: pd.DataFrame, rsa_df: pd.DataFrame) -> pd.DataFrame:

        # Merge the data
        df = pd.merge(metadata_df,rsa_df,on='sample_id',how='inner')
        
        # Drop columns
        df = df.drop(columns=['barcode','name','date','time','altitude','precision'],axis=1)

        return df

    def sql_to_clean(self) -> pd.DataFrame:
        """
        Return a complete dataframe for ML
        """
        df = self.connect_to_database()
        df = self.format_data(df)
        return df

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A script to get the data from the database.", usage="")
    parser.add_argument("-i", dest="database", required=True, help="Enter the path to the database.")
    parser.add_argument("-t",dest="table",required=True,help="Enter the RSA table.")

    args = parser.parse_args()

    samples = db_reader.DatabaseCreate(db=args.database)
    #print(samples.get_samples())

    rsa = DatabaseRSA(db=args.database,db_table=args.table)
    #print(rsa.sql_to_clean())

    df = rsa.merge_data(samples.get_samples(),rsa.sql_to_clean())
    print(df)