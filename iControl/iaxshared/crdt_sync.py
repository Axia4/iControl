import time
import uuid
from typing import Any, Dict, List, Optional, Set
import json

class LWWRegister:
    """Last-Write-Wins Register CRDT"""
    
    def __init__(self, node_id: str, value: Any = None, timestamp: float = None):
        self.node_id = node_id
        self.value = value
        self.timestamp = timestamp or time.time()
    
    def update(self, value: Any, timestamp: float = None) -> 'LWWRegister':
        """Update the register with a new value"""
        new_timestamp = timestamp or time.time()
        if new_timestamp > self.timestamp or (new_timestamp == self.timestamp and self.node_id > self.node_id):
            return LWWRegister(self.node_id, value, new_timestamp)
        return self
    
    def merge(self, other: 'LWWRegister') -> 'LWWRegister':
        """Merge with another LWW register"""
        if other.timestamp > self.timestamp:
            return other
        elif other.timestamp == self.timestamp and other.node_id > self.node_id:
            return other
        return self
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'node_id': self.node_id,
            'value': self.value,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LWWRegister':
        return cls(data['node_id'], data['value'], data['timestamp'])

class GSet:
    """Grow-only Set CRDT"""
    
    def __init__(self, elements: Set[str] = None):
        self.elements = elements or set()
    
    def add(self, element: str):
        """Add an element to the set"""
        self.elements.add(element)
    
    def contains(self, element: str) -> bool:
        """Check if element is in the set"""
        return element in self.elements
    
    def merge(self, other: 'GSet') -> 'GSet':
        """Merge with another G-Set"""
        return GSet(self.elements.union(other.elements))
    
    def to_dict(self) -> Dict[str, Any]:
        return {'elements': list(self.elements)}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GSet':
        return cls(set(data['elements']))

class SyncState:
    """Manages CRDT synchronization state - no encryption, just data sync"""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.vector_clock: Dict[str, int] = {node_id: 0}
        self.lww_registers: Dict[str, LWWRegister] = {}
        self.deleted_keys = GSet()
    
    def increment_clock(self):
        """Increment this node's logical clock"""
        self.vector_clock[self.node_id] = self.vector_clock.get(self.node_id, 0) + 1
    
    def update_clock(self, other_clock: Dict[str, int]):
        """Update vector clock with information from another node"""
        for node, clock in other_clock.items():
            self.vector_clock[node] = max(self.vector_clock.get(node, 0), clock)
        self.increment_clock()
    
    def set_value(self, key: str, value: Any):
        """Set a value using LWW semantics"""
        self.increment_clock()
        timestamp = time.time()
        
        if key in self.lww_registers:
            self.lww_registers[key] = self.lww_registers[key].update(value, timestamp)
        else:
            self.lww_registers[key] = LWWRegister(self.node_id, value, timestamp)
    
    def delete_key(self, key: str):
        """Mark a key as deleted"""
        self.increment_clock()
        self.deleted_keys.add(key)
        if key in self.lww_registers:
            del self.lww_registers[key]
    
    def get_value(self, key: str) -> Any:
        """Get a value, considering deletions"""
        if self.deleted_keys.contains(key):
            return None
        
        register = self.lww_registers.get(key)
        return register.value if register else None
    
    def merge(self, other: 'SyncState'):
        """Merge state from another node"""
        # Update vector clock
        self.update_clock(other.vector_clock)
        
        # Merge LWW registers
        for key, other_register in other.lww_registers.items():
            if key in self.lww_registers:
                self.lww_registers[key] = self.lww_registers[key].merge(other_register)
            else:
                self.lww_registers[key] = other_register
        
        # Merge deleted keys
        self.deleted_keys = self.deleted_keys.merge(other.deleted_keys)
        
        # Remove deleted keys from registers
        for deleted_key in self.deleted_keys.elements:
            if deleted_key in self.lww_registers:
                del self.lww_registers[deleted_key]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            'node_id': self.node_id,
            'vector_clock': self.vector_clock,
            'lww_registers': {k: v.to_dict() for k, v in self.lww_registers.items()},
            'deleted_keys': self.deleted_keys.to_dict()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SyncState':
        """Deserialize from dictionary"""
        state = cls(data['node_id'])
        state.vector_clock = data['vector_clock']
        state.lww_registers = {
            k: LWWRegister.from_dict(v) 
            for k, v in data['lww_registers'].items()
        }
        state.deleted_keys = GSet.from_dict(data['deleted_keys'])
        return state

class PeerSync:
    """Handles peer synchronization without encryption - just data storage and sync"""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.sync_state = SyncState(node_id)
    
    def should_sync_path(self, path: str) -> bool:
        """Check if a path should be synchronized (config._id.* pattern)"""
        return path.startswith('config.') and '._id.' in path
    
    def sync_database_changes(self, db_data: Dict[str, Any]) -> Dict[str, Any]:
        """Sync changes to database data that match sync patterns"""
        changes_made = False
        
        # Extract and sync config._id.* paths
        for table_name, table_data in db_data.items():
            if table_name == 'config' and isinstance(table_data, dict):
                for record_id, record in table_data.items():
                    if isinstance(record, dict):
                        for field_name, field_value in record.items():
                            path = f"config.{record_id}.{field_name}"
                            if self.should_sync_path(path):
                                current_value = self.sync_state.get_value(path)
                                if current_value != field_value:
                                    self.sync_state.set_value(path, field_value)
                                    changes_made = True
        
        if changes_made:
            # Apply synchronized values back to database
            self._apply_sync_to_database(db_data)
        
        return db_data
    
    def _apply_sync_to_database(self, db_data: Dict[str, Any]):
        """Apply synchronized values back to database structure"""
        if 'config' not in db_data:
            db_data['config'] = {}
        
        for path, register in self.sync_state.lww_registers.items():
            if self.should_sync_path(path) and not self.sync_state.deleted_keys.contains(path):
                parts = path.split('.')
                if len(parts) >= 3:  # config.record_id.field_name
                    table_name, record_id, field_name = parts[0], parts[1], parts[2]
                    
                    if table_name == 'config':
                        if record_id not in db_data['config']:
                            db_data['config'][record_id] = {'id': record_id}
                        
                        db_data['config'][record_id][field_name] = register.value
    
    def get_sync_data(self) -> Dict[str, Any]:
        """Get synchronization data for transmission (no encryption at peer level)"""
        sync_data = self.sync_state.to_dict()
        return {
            'source_node': self.node_id,
            'source_type': 'iSync',
            'timestamp': time.time(),
            'data': sync_data
        }
    
    def apply_sync_data(self, sync_packet: Dict[str, Any]) -> bool:
        """Apply received synchronization data"""
        try:
            # For peer servers, just merge the data without decryption
            if 'data' in sync_packet:
                other_state = SyncState.from_dict(sync_packet['data'])
                self.sync_state.merge(other_state)
                return True
        except Exception as e:
            print(f"Error applying sync data: {e}")
        
        return False
