import psycopg2
import csv
from abc import ABC, abstractmethod
from typing import Dict, List, Generator
from concurrent.futures import ThreadPoolExecutor

# Database Configuration
DB_CONFIG = {
    "dbname": "your_database",
    "user": "your_username",
    "password": "your_password",
    "host": "your_host",
    "port": "your_port"
}

# Input and output file paths
INPUT_CSV_FILE = "input.csv"
OUTPUT_CSV_FILE = "output.csv"

# Queries (Modify based on your schema)
GID_QUERY = "SELECT gid FROM your_table WHERE some_column = %s"
EID_QUERY = "SELECT eid FROM your_table WHERE another_column = %s"

# Number of concurrent database queries (Tune based on DB performance)
MAX_WORKERS = 5


# --------------------- Interface Definitions ---------------------

class IDatabase(ABC):
    """Database Interface"""
    @abstractmethod
    def execute_query(self, query: str, param: str):
        pass

    @abstractmethod
    def close(self):
        pass


class ICSVReader(ABC):
    """CSV Reader Interface"""
    @abstractmethod
    def read_rows(self) -> Generator[Dict[str, str], None, None]:
        pass


class ICSVWriter(ABC):
    """CSV Writer Interface"""
    @abstractmethod
    def write_rows(self, data: List[Dict[str, str]]):
        pass


# --------------------- Implementations ---------------------

class PostgreSQLDatabase(IDatabase):
    """Handles PostgreSQL Database connection and queries"""
    
    def __init__(self, config: Dict[str, str]):
        self.conn = psycopg2.connect(**config)
        self.cursor = self.conn.cursor()

    def execute_query(self, query: str, param: str):
        """Executes a query and returns a single value"""
        self.cursor.execute(query, (param,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def close(self):
        """Closes the database connection"""
        self.cursor.close()
        self.conn.close()


class CSVFileReader(ICSVReader):
    """Reads CSV rows in a memory-efficient way"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path

    def read_rows(self) -> Generator[Dict[str, str], None, None]:
        """Yields rows from a CSV file as dictionaries"""
        with open(self.file_path, mode="r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                yield row


class CSVFileWriter(ICSVWriter):
    """Writes CSV rows efficiently"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path

    def write_rows(self, data: List[Dict[str, str]]):
        """Writes a list of dictionaries to a CSV file"""
        if not data:
            print("No data to write.")
            return
        
        with open(self.file_path, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)


# --------------------- Main Processing Class ---------------------

class DataProcessor:
    """Processes the input CSV by querying the database and writing results to an output CSV"""
    
    def __init__(self, db: IDatabase, reader: ICSVReader, writer: ICSVWriter):
        self.db = db
        self.reader = reader
        self.writer = writer

    def process_row(self, row: Dict[str, str]) -> Dict[str, str]:
        """Processes a single row by fetching gid and eid"""
        input_gid = row.get('input_gid')
        input_eid = row.get('input_eid')

        # Fetch values from the database
        gid = self.db.execute_query(GID_QUERY, input_gid) if input_gid else None
        eid = self.db.execute_query(EID_QUERY, input_eid) if input_eid else None

        # Add new values to row
        row['gid'] = gid
        row['eid'] = eid
        return row

    def process_data(self):
        """Reads, processes, and writes data efficiently with parallel execution"""
        results = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Read and process rows concurrently
            future_to_row = {executor.submit(self.process_row, row): row for row in self.reader.read_rows()}
            
            for future in future_to_row:
                try:
                    results.append(future.result())
                except Exception as e:
                    print(f"Error processing row {future_to_row[future]}: {e}")

        # Write results to output CSV
        self.writer.write_rows(results)


# --------------------- Run the Program ---------------------

if __name__ == "__main__":
    db_instance = PostgreSQLDatabase(DB_CONFIG)
    csv_reader = CSVFileReader(INPUT_CSV_FILE)
    csv_writer = CSVFileWriter(OUTPUT_CSV_FILE)

    processor = DataProcessor(db_instance, csv_reader, csv_writer)
    
    try:
        processor.process_data()
        print(f"Processing complete. Output saved to {OUTPUT_CSV_FILE}")
    finally:
        db_instance.close()
