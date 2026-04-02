# Get the latittude and longitude from the database
import sqlite3

import numpy as np
import pandas as pd


class DatabaseCreate:
    def __init__(self, db):
        self.db = db

    def _fetch_raw_df(self) -> pd.DataFrame:

        # Connect to database
        conn = sqlite3.connect(self.db)

        query = """
                SELECT malmo_metadata.barcode, barcode_sample_map.sample_id, malmo_metadata.your_name, 
                malmo_metadata.record_location_latitude, malmo_metadata.record_location_longitude, 
                malmo_metadata.record_location_precision, malmo_metadata.start_geopoint_latitude, 
                malmo_metadata.start_geopoint_longitude, malmo_metadata.start_geopoint_altitude,malmo_metadata.start_geopoint_precision, 
                malmo_metadata.datetime_entry

                FROM barcode_sample_map 
                LEFT JOIN malmo_metadata 
                ON malmo_metadata.barcode = barcode_sample_map.barcode;

                """

        df = pd.read_sql_query(query, conn)

        conn.close()

        return df

    def _clean_df(self, df: pd.DataFrame) -> pd.DataFrame:

        df = df.dropna()
        df = df.rename(
            columns={
                "record_location_latitude": "latitude",
                "record_location_longitude": "longitude",
                "record_location_precision": "precision",
                "start_geopoint_altitude": "altitude",
                "your_name": "name",
                "datetime_entry": "datetime",
            }
        )
        df["barcode"] = df["barcode"].astype(int)
        df["latitude"] = df["latitude"].replace("", np.nan)
        df["longitude"] = df["longitude"].replace("", np.nan)
        df["precision"] = df["precision"].replace("", np.nan)

        # Fill NaN values with the start geopoint values
        df["latitude"] = df["latitude"].fillna(df["start_geopoint_latitude"])
        df["longitude"] = df["longitude"].fillna(df["start_geopoint_longitude"])
        df["precision"] = df["precision"].fillna(df["start_geopoint_precision"])

        # Drop blank samples
        df = df[df["latitude"] != ""]

        df["latitude"] = df["latitude"].astype(float)
        df["longitude"] = df["longitude"].astype(float)
        df["precision"] = df["precision"].astype(float)
        df["date"] = pd.to_datetime(df["datetime"]).dt.date
        df["time"] = pd.to_datetime(df["datetime"]).dt.time

        cols = [
            "barcode",
            "sample_id",
            "name",
            "latitude",
            "longitude",
            "altitude",
            "precision",
            "date",
            "time",
        ]

        return df[cols]

    def _assign_zones(self, df: pd.DataFrame) -> pd.DataFrame:

        # Malmo center and realistic zone centers
        zones = {
            "Zone A - Centrum": (55.6050, 13.0038),
            "Zone B - Husie": (55.5800, 13.0800),
            "Zone C - Limhamn": (55.5750, 12.9300),
            "Zone D - Rosengard": (55.5950, 13.0450),
            "Zone E - Hyllie": (55.5600, 12.9800),
            "Zone F - Kirseberg": (55.6100, 13.0500),
            "Zone G - Oxie": (55.5500, 13.0700),
            "Zone H - Fosie": (55.5700, 13.0200),
        }

        zone_names = np.array(list(zones.keys()))
        zone_coords = np.array(list(zones.values()))

        def assign_zone(lat, lon):
            # simple Euclidean distance in lat-lon space
            dists = np.sqrt((zone_coords[:, 0] - lat) ** 2 + (zone_coords[:, 1] - lon) ** 2)
            return zone_names[dists.argmin()]

        df["zone"] = df.apply(lambda r: assign_zone(r["latitude"], r["longitude"]), axis=1)

        return df

    def _fix_names(self, df: pd.DataFrame) -> pd.DataFrame:

        mapping = {
            "": "Anonymous",
            "Chandru": "Chandrashekar",
            "Wenxia ten": "Wenxia Ren",
            "Wenxia ren": "Wenxia Ren",
            "Estebsn": "Esteban",
        }
        df["name"] = df["name"].str.strip().replace(mapping)

        return df

    def get_samples(self) -> pd.DataFrame:
        """Return fully processed DataFrame with zones and fixed names."""
        df = self._fetch_raw_df()
        df = self._clean_df(df)
        df = self._assign_zones(df)
        df = self._fix_names(df)
        return df


samples = DatabaseCreate(db="./databases/malmo.db")
print(samples.get_samples())
