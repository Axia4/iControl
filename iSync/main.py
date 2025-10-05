import os
import sys
import uuid
import json
import time
import threading
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import webbrowser
from datetime import datetime

from iaxshared.iax_db import SimpleJSONDB
from iaxshared.crdt_sync import PeerSync

# Handle PyInstaller frozen executable paths
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    base_path = sys._MEIPASS
    template_folder = os.path.join(base_path, 'templates')
    static_folder = os.path.join(base_path, 'static')
else:
    # Running as normal Python script
    template_folder = 'templates'
    static_folder = 'static'

# Initialize Flask app with SocketIO
app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
app.config['SECRET_KEY'] = 'isync-supersecretkey'
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize database
DB = SimpleJSONDB('_datos/iSync.iax')
DB.create_table('config')
DB.create_table('peers')
DB.create_table('sync_history')

# Initialize CRDT sync (peers only store data, no encryption)
node_id = str(uuid.uuid4())
peer_sync = PeerSync(node_id)

# Peer management
connected_peers = {}
peer_sockets = {}

def init_config():
    """Initialize default configuration"""
    default_configs = {
        'node_id': {'key': 'node_id', 'value': node_id, 'description': 'Unique node identifier'},
        'peer_discovery_url': {'key': 'peer_discovery_url', 'value': 'https://tech.eus/isyncpeers.json', 'description': 'URL for peer discovery'},
        'auto_sync_interval': {'key': 'auto_sync_interval', 'value': '30', 'description': 'Auto sync interval in seconds'},
        'max_peers': {'key': 'max_peers', 'value': '3', 'description': 'Maximum number of connected peers'},
    }
    
    for config_key, config_data in default_configs.items():
        existing = DB.find('config', {'key': config_key})
        if not existing:
            DB.insert('config', config_data)

def get_config(key: str, default_value: str = '') -> str:
    """Get configuration value"""
    result = DB.find('config', {'key': key})
    if result:
        return result[0].get('value', default_value)
    return default_value

def set_config(key: str, value: str, description: str = '') -> None:
    """Set configuration value"""
    existing = DB.find('config', {'key': key})
    if existing:
        config_id = existing[0]['id']
        DB.update_by_id('config', config_id, {'value': value, 'description': description})
    else:
        DB.insert('config', {'key': key, 'value': value, 'description': description})

def fetch_peers_from_discovery() -> list:
    """Fetch peer list from discovery URL"""
    try:
        discovery_url = get_config('peer_discovery_url', 'https://tech.eus/isyncpeers.json')
        response = requests.get(discovery_url, timeout=10)
        response.raise_for_status()
        peers = response.json()
        return peers if isinstance(peers, list) else []
    except Exception as e:
        print(f"Error fetching peers: {e}")
        return []

def sync_with_peers():
    """Synchronize data with connected peers"""
    if not connected_peers:
        return
    
    # Get current database data
    db_data = DB.get_raw_data()
    
    # Apply local changes to sync state
    peer_sync.sync_database_changes(db_data)
    
    # Get sync packet (no encryption at peer level)
    sync_packet = peer_sync.get_sync_data()
    
    # Send to all connected peers
    for peer_id, peer_info in connected_peers.items():
        try:
            socketio.emit('sync_data', sync_packet, room=peer_info.get('socket_id'))
            print(f"Sent sync data to peer {peer_id}")
        except Exception as e:
            print(f"Error sending sync data to peer {peer_id}: {e}")

# Initialize configuration
init_config()

# Load existing node_id if available
saved_node_id = get_config('node_id')
if saved_node_id:
    node_id = saved_node_id
    peer_sync.node_id = node_id
else:
    set_config('node_id', node_id, 'Unique node identifier')

@app.route('/')
def index():
    """Main dashboard"""
    db_stats = DB.get_database_stats()
    peer_count = len(connected_peers)
    available_peers = fetch_peers_from_discovery()
    
    return render_template('index.html', 
                         db_stats=db_stats,
                         peer_count=peer_count,
                         available_peers=available_peers,
                         node_id=node_id)

@app.route('/config')
def config():
    """Configuration management"""
    configs = DB.get_all('config')
    return render_template('config.html', configs=configs)

@app.route('/config/edit/<config_id>', methods=['GET', 'POST'])
def edit_config(config_id):
    """Edit configuration"""
    config_item = DB.find_by_id('config', config_id)
    if not config_item:
        flash('Configuration not found', 'error')
        return redirect(url_for('config'))
    
    if request.method == 'POST':
        value = request.form.get('value', '')
        description = request.form.get('description', '')
        
        DB.update_by_id('config', config_id, {
            'value': value,
            'description': description
        })
        
        flash('Configuration updated successfully', 'success')
        return redirect(url_for('config'))
    
    return render_template('config_edit.html', config=config_item)

@app.route('/peers')
def peers():
    """Peer management"""
    saved_peers = DB.get_all('peers')
    available_peers = fetch_peers_from_discovery()
    
    return render_template('peers.html', 
                         saved_peers=saved_peers,
                         connected_peers=connected_peers,
                         available_peers=available_peers)

@app.route('/connect_peer', methods=['POST'])
def connect_peer():
    """Connect to a peer"""
    peer_url = request.form.get('peer_url', '').strip()
    if not peer_url:
        flash('Peer URL is required', 'error')
        return redirect(url_for('peers'))
    
    # Save peer for future connections
    existing_peer = DB.find('peers', {'url': peer_url})
    if not existing_peer:
        DB.insert('peers', {
            'url': peer_url,
            'added_at': datetime.now().isoformat(),
            'status': 'saved'
        })
    
    # Attempt connection via SocketIO client
    # This would be implemented with a SocketIO client connection
    flash(f'Connection attempt to {peer_url} initiated', 'info')
    return redirect(url_for('peers'))

@app.route('/sync_now', methods=['POST'])
def sync_now():
    """Trigger immediate synchronization"""
    sync_with_peers()
    flash('Synchronization triggered', 'success')
    return redirect(url_for('index'))

@app.route('/api/stats')
def api_stats():
    """API endpoint for statistics"""
    db_stats = DB.get_database_stats()
    return jsonify({
        'node_id': node_id,
        'connected_peers': len(connected_peers),
        'database_stats': db_stats,
        'sync_state': {
            'vector_clock': peer_sync.sync_state.vector_clock,
            'lww_registers_count': len(peer_sync.sync_state.lww_registers),
            'deleted_keys_count': len(peer_sync.sync_state.deleted_keys.elements)
        }
    })

# SocketIO event handlers
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print(f"Client connected: {request.sid}")
    emit('node_info', {'node_id': node_id})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print(f"Client disconnected: {request.sid}")
    
    # Remove from connected peers if it was a peer
    peer_to_remove = None
    for peer_id, peer_info in connected_peers.items():
        if peer_info.get('socket_id') == request.sid:
            peer_to_remove = peer_id
            break
    
    if peer_to_remove:
        del connected_peers[peer_to_remove]
        print(f"Peer {peer_to_remove} disconnected")

@socketio.on('peer_handshake')
def handle_peer_handshake(data):
    """Handle peer handshake"""
    peer_node_id = data.get('node_id')
    if peer_node_id and peer_node_id != node_id:
        connected_peers[peer_node_id] = {
            'socket_id': request.sid,
            'connected_at': time.time(),
            'node_id': peer_node_id
        }
        
        emit('handshake_response', {'node_id': node_id, 'status': 'accepted'})
        print(f"Peer {peer_node_id} connected")
        
        # Trigger sync after handshake
        threading.Timer(1.0, sync_with_peers).start()

@socketio.on('sync_data')
def handle_sync_data(data):
    """Handle incoming synchronization data"""
    try:
        # Peers just store and sync data without decryption
        if peer_sync.apply_sync_data(data):
            # Apply changes to database
            db_data = DB.get_raw_data()
            peer_sync.sync_database_changes(db_data)
            DB.set_raw_data(db_data)
            
            print(f"Applied sync data from {data.get('source_node', 'unknown')}")
            
            # Record sync history
            DB.insert('sync_history', {
                'peer_node_id': data.get('source_node', 'unknown'),
                'timestamp': datetime.now().isoformat(),
                'status': 'success'
            })
        else:
            print("Failed to apply sync data")
            
    except Exception as e:
        print(f"Error handling sync data: {e}")

@socketio.on('request_sync')
def handle_sync_request():
    """Handle sync request from peer"""
    sync_with_peers()

def auto_sync_worker():
    """Background worker for automatic synchronization"""
    while True:
        try:
            interval = int(get_config('auto_sync_interval', '30'))
            time.sleep(interval)
            
            if connected_peers:
                sync_with_peers()
                
        except Exception as e:
            print(f"Auto sync error: {e}")
            time.sleep(30)

if __name__ == '__main__':
    # Start auto sync worker
    auto_sync_thread = threading.Thread(target=auto_sync_worker, daemon=True)
    auto_sync_thread.start()
    
    if os.environ.get('FLASK_ENV') == 'development' or sys.argv[1:] == ['--dev']:
        app.config['TEMPLATES_AUTO_RELOAD'] = True
        socketio.run(app, port=5002, debug=True)
    else:
        if hasattr(sys, 'frozen'):
            # Open the web browser automatically when running as a frozen executable
            webbrowser.open("http://localhost:5342")
        socketio.run(app, host='0.0.0.0', port=5342, debug=False)
