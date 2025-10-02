#!/usr/bin/env python3

print("Testing simple database...")

import json
import os

class SimpleDB:
    def __init__(self, filename):
        self.filename = filename
        self._data = {}
        
        print(f"Initializing database at {filename}")
        
        # Ensure directory exists (only if filename contains a directory path)
        dirname = os.path.dirname(filename)
        if dirname:
            print(f"Creating directory: {dirname}")
            os.makedirs(dirname, exist_ok=True)
        
        # Try to load existing data
        if os.path.exists(filename):
            print(f"Loading existing file: {filename}")
            with open(filename, 'r') as f:
                self._data = json.load(f)
        else:
            print(f"Creating new file: {filename}")
            self._data = {}

    def save(self):
        print(f"Saving to {self.filename}")
        with open(self.filename, 'w') as f:
            json.dump(self._data, f, indent=2)
        print("Save completed")

    def create_table(self, table):
        print(f"Creating table: {table}")
        if table not in self._data:
            self._data[table] = {}
            self.save()
        print(f"Table {table} ready")

try:
    print("Creating database...")
    db = SimpleDB('simple_test.json')
    print("✓ Database created")
    
    print("Creating table...")
    db.create_table('test')
    print("✓ Table created")
    
    print("All tests passed!")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
