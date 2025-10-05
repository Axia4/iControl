import json
import requests
import threading
import time
from typing import Dict, List, Any, Optional
import socketio
from urllib.parse import urlparse

class iSyncClient:
    """Client for connecting iControl to iSync peers"""
    
    def __init__(self, db_instance, node_id: str = None):
        self.db = db_instance
        self.node_id = node_id or f"icontrol-{int(time.time())}"
        self.connected_peers: Dict[str, socketio.SimpleClient] = {}
        self.peer_urls: List[str] = []
        self.sync_enabled = False
        self.last_sync_time = 0
        
    def fetch_peer_list(self, discovery_url: str = "https://tech.eus/isyncpeers.json") -> List[Dict[str, Any]]:
        """Fetch list of available iSync peers"""
        try:
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
                    threading.Timer(2.0, lambda: self.sync_to_peer(peer_url)).start()
            
            # Connect to peer
            sio.connect(peer_url)
            self.connected_peers[peer_url] = sio
            return True
            
        except Exception as e:
            print(f"Error connecting to peer {peer_url}: {e}")
            return False
    
    def disconnect_from_peer(self, peer_url: str):
        """Disconnect from a specific peer"""
        if peer_url in self.connected_peers:
            try:
                self.connected_peers[peer_url].disconnect()
            except:
                pass
            del self.connected_peers[peer_url]
    
    def connect_to_peers(self, peer_urls: List[str]):
        """Connect to multiple peers"""
        self.peer_urls = peer_urls[:3]  # Limit to 3 peers as requested
        
        for peer_url in self.peer_urls:
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
    
    def prepare_sync_data(self) -> Dict[str, Any]:
        """Prepare iControl data for synchronization"""
        # Get only config data that matches sync patterns
        sync_data = self.db.get_encrypted_sync_data()
        
        # Add top-level _encrypted flag and metadata
        return {
            "_encrypted": True,
            "source_node": self.node_id,
            "source_type": "iControl",
            "timestamp": time.time(),
            "data": sync_data
        }
    
    def sync_to_peer(self, peer_url: str):
        """Send sync data to a specific peer"""
        if peer_url not in self.connected_peers:
            return False
        
        try:
            sync_packet = self.prepare_sync_data()
            self.connected_peers[peer_url].emit('sync_data', sync_packet)
            print(f"Sent sync data to {peer_url}")
            return True
        except Exception as e:
            print(f"Error syncing to peer {peer_url}: {e}")
            return False
    
    def sync_to_all_peers(self):
        """Send sync data to all connected peers"""
        if not self.connected_peers:
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
            
            sync_data = data.get("data", {})
            if sync_data and self.db.apply_encrypted_sync_data(sync_data):
                print(f"Applied sync data from {from_peer} (node: {data.get('source_node', 'unknown')})")
            else:
                print(f"Failed to apply sync data from {from_peer}")
                
        except Exception as e:
            print(f"Error handling incoming sync from {from_peer}: {e}")
    
    def start_auto_sync(self, interval: int = 30):
        """Start automatic synchronization"""
        self.sync_enabled = True
        
        def sync_worker():
            while self.sync_enabled:
                try:
                    if self.connected_peers:
                        synced_count = self.sync_to_all_peers()
                        if synced_count > 0:
                            print(f"Auto-sync completed to {synced_count} peers")
                    time.sleep(interval)
                except Exception as e:
                    print(f"Auto-sync error: {e}")
                    time.sleep(interval)
        
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
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status"""
        return {
            "node_id": self.node_id,
            "connected_peers": len(self.connected_peers),
            "peer_urls": self.peer_urls,
            "connected_to": list(self.connected_peers.keys()),
            "sync_enabled": self.sync_enabled,
            "last_sync_time": self.last_sync_time
        }
    
    def force_sync_now(self) -> Dict[str, Any]:
        """Force immediate synchronization and return results"""
        if not self.connected_peers:
            return {"status": "error", "message": "No peers connected"}
        
        synced_count = self.sync_to_all_peers()
        return {
            "status": "success", 
            "message": f"Synced to {synced_count} of {len(self.connected_peers)} peers",
            "synced_peers": synced_count,
            "total_peers": len(self.connected_peers)
        }
