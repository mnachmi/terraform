"""
o3_mini_high/
├── config.py
├── main.py
├── requirements.txt
├── database/
│   ├── __init__.py
│   ├── db.py
│   └── queries.py
├── csv_handler/
│   ├── __init__.py
│   ├── reader.py
│   └── writer.py
└── processor/
    ├── __init__.py
    └── processor.py
"""

# config.py
DB_CONFIG = {
    "dbname": "your_database",
    "user": "your_username",
    "password": "your_password",
    "host": "your_host",
    "port": "your_port"
}

INPUT_CSV_FILE = "input.csv"   # Input CSV should contain at least 'input_gid' and 'input_eid' columns
OUTPUT_CSV_FILE = "output.csv"

# SQL queries to fetch gid and eid. Adjust these queries according to your schema.
GID_QUERY = "SELECT gid FROM your_table WHERE some_column = %s"
EID_QUERY = "SELECT eid FROM your_table WHERE another_column = %s"

# Number of workers to use for parallel processing
MAX_WORKERS = 5

# database/db.py
import psycopg2
from abc import ABC, abstractmethod

class IDatabase(ABC):
    """Abstract interface for database operations."""
    @abstractmethod
    def execute_query(self, query: str, param: str):
        pass

    @abstractmethod
    def close(self):
        pass

class PostgreSQLDatabase(IDatabase):
    """Implementation of IDatabase for PostgreSQL."""
    def __init__(self, config: dict):
        self.conn = psycopg2.connect(**config)
        self.cursor = self.conn.cursor()

    def execute_query(self, query: str, param: str):
        self.cursor.execute(query, (param,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def close(self):
        self.cursor.close()
        self.conn.close()

# csv_handler/reader.py
import csv
from abc import ABC, abstractmethod
from typing import Generator, Dict

class ICSVReader(ABC):
    """Abstract interface for reading CSV files."""
    @abstractmethod
    def read_rows(self) -> Generator[Dict[str, str], None, None]:
        pass

class CSVFileReader(ICSVReader):
    """Streaming CSV reader that yields one row (as a dict) at a time."""
    def __init__(self, file_path: str):
        self.file_path = file_path

    def read_rows(self) -> Generator[Dict[str, str], None, None]:
        with open(self.file_path, mode="r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                yield row

# csv_handler/writer.py
import csv
from abc import ABC, abstractmethod
from typing import List, Dict

class ICSVWriter(ABC):
    """Abstract interface for writing CSV files."""
    @abstractmethod
    def write_rows(self, data: List[Dict[str, str]]):
        pass

class CSVFileWriter(ICSVWriter):
    """Writes a list of dictionaries to a CSV file."""
    def __init__(self, file_path: str):
        self.file_path = file_path

    def write_rows(self, data: List[Dict[str, str]]):
        if not data:
            print("No data to write.")
            return
        with open(self.file_path, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
# processor/processor.py
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List
from database.db import IDatabase
from csv_handler.reader import ICSVReader
from csv_handler.writer import ICSVWriter
from config import GID_QUERY, EID_QUERY, MAX_WORKERS

class DataProcessor:
    """
    Processes CSV data by:
      - Reading input rows.
      - Executing database queries (in parallel) to fetch gid and eid.
      - Writing the processed rows to an output CSV.
    """
    def __init__(self, db: IDatabase, reader: ICSVReader, writer: ICSVWriter):
        self.db = db
        self.reader = reader
        self.writer = writer

    def process_row(self, row: Dict[str, str]) -> Dict[str, str]:
        """Processes a single row by querying the database for gid and eid."""
        input_gid = row.get('input_gid')
        input_eid = row.get('input_eid')

        # Query the database if the input value is present
        gid = self.db.execute_query(GID_QUERY, input_gid) if input_gid else None
        eid = self.db.execute_query(EID_QUERY, input_eid) if input_eid else None

        # Append the new values to the row
        row['gid'] = gid
        row['eid'] = eid
        return row

    def process_data(self):
        """
        Reads rows from the CSV, processes each row in parallel using a thread pool,
        and writes the results to the output CSV.
        """
        results: List[Dict[str, str]] = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Schedule processing for each row concurrently.
            future_to_row = {executor.submit(self.process_row, row): row for row in self.reader.read_rows()}
            for future in future_to_row:
                try:
                    processed_row = future.result()
                    results.append(processed_row)
                except Exception as e:
                    print(f"Error processing row {future_to_row[future]}: {e}")
        self.writer.write_rows(results)
# main.py
from config import DB_CONFIG, INPUT_CSV_FILE, OUTPUT_CSV_FILE
from database.db import PostgreSQLDatabase
from csv_handler.reader import CSVFileReader
from csv_handler.writer import CSVFileWriter
from processor.processor import DataProcessor

def main():
    db_instance = PostgreSQLDatabase(DB_CONFIG)
    csv_reader = CSVFileReader(INPUT_CSV_FILE)
    csv_writer = CSVFileWriter(OUTPUT_CSV_FILE)
    processor = DataProcessor(db_instance, csv_reader, csv_writer)

    try:
        processor.process_data()
        print(f"Processing complete. Output saved to {OUTPUT_CSV_FILE}")
    finally:
        db_instance.close()

if __name__ == "__main__":
    main()
