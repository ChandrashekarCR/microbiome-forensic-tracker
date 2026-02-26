import sqlite3
from pathlib import Path

DB_PATH = "/home/chandru/binp51/database/malmo.db"

# Get database connection
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Insert samples from the user input into the table
def insert_sample(
        user: str,
        email: str,
        sample_name: str,
        r1_path: str,
        r2_path: str
):
    # Insert a new sample into database
    conn = get_db()
    cursor = conn.execute(
        """
        INSERT INTO SAMPLES (user, email, sample_name, r1_path, r2_path)
        VALUES (?, ?, ?, ?, ?)
        """, (user, email, sample_name, r1_path, r2_path)
    )
    conn.commit()
    sample_id =  cursor.lastrowid
    conn.close()
    return sample_id

# Update the sample status
def update_sample_status(sample_id: int, status:str, **kwargs):
    pass