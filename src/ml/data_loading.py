# Importing libraries
import argparse
import sqlite3

import pandas as pd


class DatabaseRSA:
    def __init__(self, db):
        self.db = db

    def connect_to_database(self) -> pd.DataFrame:

        # Connect to database
        conn = sqlite3.connect(self.db)

        query = """
                SELECT * FROM malmo_phylum;
                """

        df = pd.read_sql_query(query, conn)

        conn.close()

        return df

    def format_data(self, df: pd.DataFrame) -> pd.DataFrame:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A script to get the data from the database.", usage="")
    parser.add_argument("-i", dest="database", required=True, help="Enter the path to the database.")

    args = parser.parse_args()

    # samples = db_reader.DatabaseCreate(db=args.database)
    # print(samples.get_samples())

    rsa = DatabaseRSA(db=args.database)
    print(rsa.connect_to_database().head())
