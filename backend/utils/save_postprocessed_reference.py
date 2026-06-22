import json
import os
import re
import sys
import uuid
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from seed_defaults import seed_enum_defaults

class DatabaseInsertionStep:
    """Pipeline step for inserting JSON data into PostgreSQL database."""
    
    def __init__(self, response: str):
        """
        Initialize the database insertion step.
        
        Args:
            response: The raw response string containing JSON data
        """
        self.response = response
        self.data = None
        self.id_remap = {}
        self.conn = None
        
        # Load environment variables
        load_dotenv(os.path.join(os.getcwd(), "..", ".env"))
        
        # Configuration
        self.insertion_order = [
            "clients",            # no FK deps
            "offers",             # → clients
            "avatars",            # → clients
            "mechanisms",         # → clients
            "proof_bank",         # → clients
            "angles",             # → clients
            "hooks",              # → clients
            "script_frameworks",  # no FK deps
            "constraints",        # → clients
            "pain_points",        # → avatars
            # "ideas" is intentionally excluded: the ideas table is populated
            # exclusively by the ideation pipeline, never from extraction.
        ]
        
        self.jsonb_cols = {"structure"}  # columns that need to be serialised as JSONB
        
    def parse_json(self) -> Dict[str, Any]:
        """Parse JSON from response, stripping markdown fences."""
        raw = self.response.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if match:
            raw = match.group(1).strip()
        return json.loads(raw)
    
    def remap_ids(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remap Gemini-generated IDs to valid UUIDs."""
        # Build mapping from Gemini IDs to valid UUIDs
        for table_rows in data.values():
            for row in table_rows:
                old_id = row.get("id")
                if old_id and old_id not in self.id_remap:
                    self.id_remap[old_id] = str(uuid.uuid4())
        
        def remap_row(row: Dict[str, Any]) -> Dict[str, Any]:
            """Replace any value that appears in the remap dict."""
            return {
                k: self.id_remap[v] if isinstance(v, str) and v in self.id_remap else v
                for k, v in row.items()
            }
        
        # Apply remapping to all rows
        for table in data:
            data[table] = [remap_row(row) for row in data[table]]
        
        return data
    
    def connect_database(self) -> psycopg2.extensions.connection:
        """Establish database connection."""
        return psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            dbname=os.getenv("POSTGRES_DB", "app_db"),
            user=os.getenv("POSTGRES_USER", "app_user"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
        )
    
    def prepare_values(self, row: Dict[str, Any], columns: List[str]) -> tuple:
        """Prepare row values for insertion, handling JSONB columns."""
        return tuple(
            psycopg2.extras.Json(row[col])
            if col in self.jsonb_cols and isinstance(row[col], (dict, list))
            else row[col]
            for col in columns
        )
    
    def insert_tables(self, data: Dict[str, Any]) -> Dict[str, int]:
        """Insert data into tables in FK-safe order."""
        results = {}
        
        try:
            with self.conn:
                with self.conn.cursor() as cur:
                    for table in self.insertion_order:
                        rows = data.get(table, [])
                        if not rows:
                            print(f"  {table}: skipped (empty)")
                            results[table] = 0
                            continue
                        
                        # Prepare SQL statement
                        columns = list(rows[0].keys())
                        col_str = ", ".join(columns)
                        ph_str = ", ".join(["%s"] * len(columns))
                        sql = (
                            f"INSERT INTO {table} ({col_str}) "
                            f"VALUES ({ph_str}) "
                            f"ON CONFLICT (id) DO NOTHING"
                        )
                        
                        # Prepare values
                        values = [
                            self.prepare_values(row, columns)
                            for row in rows
                        ]
                        
                        # Execute insertion
                        cur.executemany(sql, values)
                        results[table] = len(rows)
                        print(f"  {table}: {len(rows)} row(s) inserted")

                    seed_enum_defaults(cur)

        except Exception as e:
            print(f"\nFailed during insertion: {e}")
            raise
        
        return results
    
    def run(self) -> Dict[str, int]:
        """
        Execute the entire database insertion pipeline.
        
        Returns:
            Dictionary mapping table names to number of rows inserted
        """
        try:
            print("Starting database insertion pipeline...")
            
            # Step 1: Parse JSON
            print("  Parsing JSON data...")
            self.data = self.parse_json()
            print(f"  Found {len(self.data)} tables")
            
            # Step 2: Remap IDs
            print("  Remapping IDs to valid UUIDs...")
            self.data = self.remap_ids(self.data)
            print(f"  Remapped {len(self.id_remap)} IDs")
            
            # Step 3: Connect to database
            print("  Connecting to database...")
            self.conn = self.connect_database()
            
            # Step 4: Insert data
            print("  Inserting data...")
            results = self.insert_tables(self.data)
            
            results["_client_ids"] = [
                row["id"] for row in self.data.get("clients", [])
            ]
            print("\nDone — all tables saved.")
            return results
            
        except json.JSONDecodeError as e:
            print(f"\nFailed to parse JSON: {e}")
            raise
        except psycopg2.Error as e:
            print(f"\nDatabase error: {e}")
            raise
        except Exception as e:
            print(f"\nUnexpected error: {e}")
            raise
        finally:
            if self.conn:
                self.conn.close()
    
    def close(self):
        """Close database connection if open."""
        if self.conn and not self.conn.closed:
            self.conn.close()