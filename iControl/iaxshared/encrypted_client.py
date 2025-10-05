import json
import time
from typing import Dict, List, Any, Optional
from cryptography.fernet import Fernet
import base64
import socketio
from urllib.parse import urlparse

from .crdt_sync import SyncState, LWWRegister

class EncryptedClient:
    """Client for iControl that encrypts data with isync_token before sending to peers"""
    
    def __init__(self, db_instance, node_id: str = None, isync_token: str = None):
        self.db = db_instance
        self.node_id = node_id or f"icontrol-{int(time.time())}"
        self.sync_state = SyncState(self.node_id)
        
        # Set up encryption with isync_token
        self.isync_token = isync_token
        self.cipher = None
        if isync_token:
            self._setup_encryption(isync_token)
        
        self.connected_peers: Dict[str, socketio.SimpleClient] = {}
        self.peer_urls: List[str] = []
        self.sync_enabled = False
        self.last_sync_time = 0
    
    def _setup_encryption(self, token: str):
        """Setup encryption cipher from isync_token"""
        try:
            # Use token as base for encryption key generation
            # Hash the token to create a consistent 32-byte key
            import hashlib
            key_bytes = hashlib.sha256(token.encode('utf-8')).digest()
            # Use first 32 bytes for Fernet key (base64 encoded)
            fernet_key = base64.urlsafe_b64encode(key_bytes)
            self.cipher = Fernet(fernet_key)
            print(f"Encryption setup successful with token")
        except Exception as e:
            print(f"Failed to setup encryption: {e}")
            self.cipher = None
    
    def set_isync_token(self, token: str):
        """Update the isync_token and reconfigure encryption"""
        self.isync_token = token
        self._setup_encryption(token)
    
    def encrypt_data(self, data: Any) -> str:
        """Encrypt data for transmission"""
        if not self.cipher:
            raise Exception("No encryption cipher available - isync_token not set")
        
        json_data = json.dumps(data, ensure_ascii=False)
        encrypted = self.cipher.encrypt(json_data.encode('utf-8'))
        return base64.b64encode(encrypted).decode('ascii')
    
    def decrypt_data(self, encrypted_data: str) -> Any:
        """Decrypt received data"""
        if not self.cipher:
            print("Cannot decrypt - no isync_token set")
            return None
        
        try:
            encrypted_bytes = base64.b64decode(encrypted_data.encode('ascii'))
            decrypted = self.cipher.decrypt(encrypted_bytes)
            return json.loads(decrypted.decode('utf-8'))
        except Exception as e:
            print(f"Decryption error: {e}")
            return None
    
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
    
    def prepare_sync_data(self) -> Dict[str, Any]:
        """Prepare encrypted sync data for transmission"""
        if not self.cipher:
            raise Exception("Cannot prepare sync data - no isync_token set")
        
        # Get sync state
        sync_data = self.sync_state.to_dict()
        
        # Encrypt the data
        encrypted_data = self.encrypt_data(sync_data)
        
        # Add top-level _encrypted flag and metadata
        return {
            "_encrypted": True,
            "source_node": self.node_id,
            "source_type": "iControl",
            "timestamp": time.time(),
            "encrypted_data": encrypted_data
        }
    
    def fetch_peer_list(self, discovery_url: str = "https://tech.eus/isyncpeers.json") -> List[Dict[str, Any]]:
        """Fetch list of available iSync peers"""
        try:
            import requests
            response = requests.get(discovery_url, timeout=10)
            response.raise_for_status()
            peers = response.json()
            return peers if isinstance(peers, list) else []
        except Exception as e:
            print(f"Error fetching peer list: {e}")
            return []
    
    def select_peers(self, peer_list: List[Dict[str, Any]], max_peers: int = 3) -> List[str]:
        """Select up to max_peers URLs from the peer list"""
        if not peer_list:
            return []
        
        # Prioritize verified peers, then sort by name
        sorted_peers = sorted(peer_list, key=lambda p: (not p.get('verified', False), p.get('name', '')))
        selected = sorted_peers[:max_peers]
        
        return [peer.get('url', '') for peer in selected if peer.get('url')]
    
    def connect_to_peer(self, peer_url: str) -> bool:
        """Connect to a single iSync peer via SocketIO"""
        try:
            # Parse URL to get host and port
            parsed = urlparse(peer_url)
            if not parsed.scheme or not parsed.netloc:
                print(f"Invalid peer URL: {peer_url}")
                return False
            
            # Create SocketIO client
            sio = socketio.SimpleClient()
            
            # Set up event handlers
            @sio.event
            def connect():
                print(f"Connected to peer: {peer_url}")
                # Send handshake
                sio.emit('peer_handshake', {'node_id': self.node_id})
            
            @sio.event
            def disconnect():
                print(f"Disconnected from peer: {peer_url}")
                if peer_url in self.connected_peers:
                    del self.connected_peers[peer_url]
            
            @sio.event
            def sync_data(data):
                self.handle_incoming_sync(data, peer_url)
            
            @sio.event
            def handshake_response(data):
                if data.get('status') == 'accepted':
                    print(f"Handshake accepted by peer: {peer_url}")
                    # Trigger initial sync
                    import threading
                    threading.Timer(2.0, lambda: self.sync_to_peer(peer_url)).start()
            
            # Connect to peer
            sio.connect(peer_url)
            self.connected_peers[peer_url] = sio
            return True
            
        except Exception as e:
            print(f"Error connecting to peer {peer_url}: {e}")
            return False
    
    def sync_to_peer(self, peer_url: str):
        """Send encrypted sync data to a specific peer"""
        if peer_url not in self.connected_peers:
            return False
        
        try:
            if not self.cipher:
                print("Cannot sync - no isync_token set")
                return False
            
            sync_packet = self.prepare_sync_data()
            self.connected_peers[peer_url].emit('sync_data', sync_packet)
            print(f"Sent encrypted sync data to {peer_url}")
            return True
        except Exception as e:
            print(f"Error syncing to peer {peer_url}: {e}")
            return False
    
    def sync_to_all_peers(self):
        """Send encrypted sync data to all connected peers"""
        if not self.connected_peers:
            return 0
        
        if not self.cipher:
            print("Cannot sync - no isync_token set")
            return 0
        
        successful_syncs = 0
        for peer_url in list(self.connected_peers.keys()):
            if self.sync_to_peer(peer_url):
                successful_syncs += 1
        
        self.last_sync_time = time.time()
        return successful_syncs
    
    def handle_incoming_sync(self, data: Dict[str, Any], from_peer: str):
        """Handle incoming synchronization data"""
        try:
            if not data.get("_encrypted", False):
                print(f"Received non-encrypted sync data from {from_peer}, ignoring")
                return
            
            if data.get("source_type") == "iControl" and data.get("source_node") == self.node_id:
                # Ignore our own data echoed back
                return
            
            if not self.cipher:
                print("Cannot decrypt incoming sync - no isync_token set")
                return
            
            # Decrypt the data
            encrypted_data = data.get("encrypted_data", "")
            if not encrypted_data:
                print("No encrypted data in sync packet")
                return
            
            decrypted_data = self.decrypt_data(encrypted_data)
            if decrypted_data is None:
                print(f"Failed to decrypt sync data from {from_peer}")
                return
            
            # Apply the decrypted sync data
            other_state = SyncState.from_dict(decrypted_data)
            self.sync_state.merge(other_state)
            
            # Apply to database
            db_data = self.db.get_raw_data()
            self.sync_database_changes(db_data)
            self.db.set_raw_data(db_data)
            
            print(f"Applied encrypted sync data from {from_peer} (node: {data.get('source_node', 'unknown')})")
                
        except Exception as e:
            print(f"Error handling incoming sync from {from_peer}: {e}")
    
    def connect_to_peers(self, peer_urls: List[str]):
        """Connect to multiple peers"""
        self.peer_urls = peer_urls[:3]  # Limit to 3 peers as requested
        
        for peer_url in self.peer_urls:
            import threading
            threading.Thread(
                target=self.connect_to_peer, 
                args=(peer_url,), 
                daemon=True
            ).start()
            time.sleep(1)  # Small delay between connections
    
    def auto_discover_and_connect(self):
        """Automatically discover and connect to peers"""
        peer_list = self.fetch_peer_list()
        if peer_list:
            selected_peers = self.select_peers(peer_list, 3)
            if selected_peers:
                print(f"Auto-connecting to peers: {selected_peers}")
                self.connect_to_peers(selected_peers)
                return True
        return False
    
    def start_auto_sync(self, interval: int = 30):
        """Start automatic synchronization"""
        self.sync_enabled = True
        
        def sync_worker():
            while self.sync_enabled:
                try:
                    if self.connected_peers and self.cipher:
                        synced_count = self.sync_to_all_peers()
                        if synced_count > 0:
                            print(f"Auto-sync completed to {synced_count} peers")
                    time.sleep(interval)
                except Exception as e:
                    print(f"Auto-sync error: {e}")
                    time.sleep(interval)
        
        import threading
        threading.Thread(target=sync_worker, daemon=True).start()
        print(f"Auto-sync started with {interval}s interval")
    
    def stop_auto_sync(self):
        """Stop automatic synchronization"""
        self.sync_enabled = False
        print("Auto-sync stopped")
    
    def disconnect_all(self):
        """Disconnect from all peers"""
        self.stop_auto_sync()
        for peer_url in list(self.connected_peers.keys()):
            self.disconnect_from_peer(peer_url)
        print("Disconnected from all peers")
    
    def disconnect_from_peer(self, peer_url: str):
        """Disconnect from a specific peer"""
        if peer_url in self.connected_peers:
            try:
                self.connected_peers[peer_url].disconnect()
            except:
                pass
            del self.connected_peers[peer_url]
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status"""
        return {
            "node_id": self.node_id,
            "connected_peers": len(self.connected_peers),
            "peer_urls": self.peer_urls,
            "connected_to": list(self.connected_peers.keys()),
            "sync_enabled": self.sync_enabled,
            "last_sync_time": self.last_sync_time,
            "has_token": bool(self.isync_token),
            "encryption_ready": bool(self.cipher)
        }
    
    def force_sync_now(self) -> Dict[str, Any]:
        """Force immediate synchronization and return results"""
        if not self.connected_peers:
            return {"status": "error", "message": "No peers connected"}
        
        if not self.cipher:
            return {"status": "error", "message": "No isync_token set - cannot encrypt data"}
        
        synced_count = self.sync_to_all_peers()
        return {
            "status": "success", 
            "message": f"Synced to {synced_count} of {len(self.connected_peers)} peers",
            "synced_peers": synced_count,
            "total_peers": len(self.connected_peers)
        }
