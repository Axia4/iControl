import json
import os
import threading
import uuid
from typing import Any, Dict, List, Optional, Union

class SimpleJSONDB:
    def __init__(self, filename: str):
        self.filename = filename
        self._lock = threading.Lock()
        self._data = {}
        
        # Ensure directory exists (only if filename contains a directory path)
        dirname = os.path.dirname(filename)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        
        # Try to load existing data
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    data = json.load(f)
                    # Simple migration check
                    if data:
                        self._data = self._migrate_data(data)
                    else:
                        self._data = {}
            except json.JSONDecodeError as e:
                print(f"Warning: Error reading JSON file {filename}: {e}")
                print("Creating new database file")
                self._data = {}
        else:
            self._data = {}

    def _migrate_data(self, data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Migrate old list-based tables to dict-based tables"""
        if not data:
            return {}
            
        migrated = {}
        
        for table_name, table_data in data.items():
            # Safety check
            if table_data is None:
                migrated[table_name] = {}
                continue
                
            if isinstance(table_data, list):
                migrated[table_name] = {}
                
                for i, record in enumerate(table_data):
                    if not isinstance(record, dict):
                        continue
                        
                    if 'id' in record:
                        migrated[table_name][str(record['id'])] = record
                    else:
                        # Generate new ID if none exists
                        new_id = str(uuid.uuid4())
                        record['id'] = new_id
                        migrated[table_name][new_id] = record
                        
            elif isinstance(table_data, dict):
                migrated[table_name] = table_data
            else:
                migrated[table_name] = {}
                
        return migrated

    def save(self):
        try:
            with open(self.filename, 'w') as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            print(f"Error saving to {self.filename}: {e}")
            raise

    def create_table(self, table: str):
        if table not in self._data:
            self._data[table] = {}
            self.save()

    def insert(self, table: str, record: Dict[str, Any]) -> str:
        """Insert a record and return the generated ID"""
        # Generate ID if not provided
        if 'id' not in record:
            record_id = str(uuid.uuid4())
            record['id'] = record_id
        else:
            record_id = str(record['id'])
        
        self._data.setdefault(table, {})[record_id] = record
        self.save()
        return record_id

    def find_by_id(self, table: str, record_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Fast O(1) lookup by ID"""
        table_data = self._data.get(table, {})
        record = table_data.get(str(record_id))
        return record.copy() if record else None

    def find(self, table: str, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        table_data = self._data.get(table, {})
        records = list(table_data.values())
        if not query:
            return [r.copy() for r in records]
        return [r.copy() for r in records if all(r.get(k) == v for k, v in query.items())]

    def update(self, table: str, query: Dict[str, Any], updates: Dict[str, Any]):
        updated = 0
        table_data = self._data.get(table, {})
        for record in table_data.values():
            if all(record.get(k) == v for k, v in query.items()):
                record.update(updates)
                updated += 1
        if updated:
            self.save()
        return updated

    def update_by_id(self, table: str, record_id: Union[str, int], updates: Dict[str, Any]) -> bool:
        """Fast O(1) update by ID"""
        table_data = self._data.get(table, {})
        record_id_str = str(record_id)
        if record_id_str in table_data:
            table_data[record_id_str].update(updates)
            self.save()
            return True
        return False

    def delete(self, table: str, query: Dict[str, Any]):
        table_data = self._data.get(table, {})
        before = len(table_data)
        to_delete = []
        for record_id, record in table_data.items():
            if all(record.get(k) == v for k, v in query.items()):
                to_delete.append(record_id)
        
        for record_id in to_delete:
            del table_data[record_id]
        
        after = len(table_data)
        if before != after:
            self.save()
        return before - after

    def delete_by_id(self, table: str, record_id: Union[str, int]) -> bool:
        """Fast O(1) delete by ID"""
        table_data = self._data.get(table, {})
        record_id_str = str(record_id)
        if record_id_str in table_data:
            del table_data[record_id_str]
            self.save()
            return True
        return False

    def drop_table(self, table: str):
        if table in self._data:
            del self._data[table]
            self.save()

    def get_all(self, table: str) -> Dict[str, Dict[str, Any]]:
        """Get all records in a table as a dict of {id: record}"""
        table_data = self._data.get(table, {})
        return {k: v.copy() for k, v in table_data.items()}

    def count(self, table: str) -> int:
        """Get count of records in a table"""
        return len(self._data.get(table, {}))

    def exists(self, table: str, record_id: Union[str, int]) -> bool:
        """Check if a record exists by ID"""
        table_data = self._data.get(table, {})
        return str(record_id) in table_data

# Example usage:
# db = SimpleJSONDB('mydb.json')
# db.create_table('users')
# 
# # Insert returns the generated ID
# user_id = db.insert('users', {'name': 'Alice', 'age': 30})
# 
# # Fast O(1) lookup by ID
# user = db.find_by_id('users', user_id)
# 
# # Traditional query-based operations still work
# users = db.find('users', {'name': 'Alice'})
# 
# # Fast O(1) update by ID
# db.update_by_id('users', user_id, {'age': 31})
# 
# # Traditional update still works
# db.update('users', {'name': 'Alice'}, {'age': 32})
# 
# # Fast O(1) delete by ID
# db.delete_by_id('users', user_id)
# 
# # Traditional delete still works
# db.delete('users', {'name': 'Alice'})
# 
# db.drop_table('users')