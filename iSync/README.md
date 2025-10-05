# iSync - Encrypted Mesh Data Synchronization

iSync is a third application in the iControl suite that provides encrypted, mesh-like data synchronization using Flask-SocketIO and Conflict-free Replicated Data Types (CRDT).

## Architecture

### Components

1. **iSync Standalone Application** (`/iSync/`)
   - Independent Flask-SocketIO server
   - Peer discovery and management
   - CRDT-based conflict resolution
   - Encrypted data transmission

2. **iControl Integration** (`/iControl/iaxshared/isync_client.py`)
   - SocketIO client for connecting to iSync peers
   - Selective data synchronization
   - Configuration management

3. **Shared Database Layer** (`/iaxshared/iax_db.py`)
   - Enhanced with sync-specific methods
   - Supports encrypted data paths
   - Compatible with existing data structures

## Key Features

### 🔐 Encryption
- All synchronized data is encrypted using Fernet (AES 128)
- Each peer has a unique encryption key
- Top-level `"_encrypted": True` flag for packet identification
- Base64 encoded keys for easy sharing

### 🌐 Mesh Networking
- Automatic peer discovery from `https://tech.eus/isyncpeers.json`
- Manual peer configuration support
- Up to 3 simultaneous peer connections
- Resilient to peer disconnections

### 📊 CRDT Synchronization
- Last-Write-Wins (LWW) registers for conflict resolution
- Vector clocks for causality tracking
- Grow-only sets for deletions
- Eventual consistency guarantee

### 🎯 Selective Sync
- Only synchronizes paths matching `config._id.*` pattern
- Preserves compatibility with existing data
- Minimal overhead on non-sync data

## Installation & Setup

### 1. Install Dependencies
```bash
pip install cryptography pynacl flask-socketio python-socketio
```

### 2. Start iSync Application
```bash
cd iSync
python main.py --dev  # Development mode
python main.py        # Production mode (port 5342)
```

### 3. Enable iSync in iControl
1. Navigate to `/isync` in iControl
2. Click "Habilitar iSync"
3. Configure peers (auto-discovery or manual)

## Configuration

### iSync Standalone (`/iSync/`)
- **Port:** 5342 (production), 5002 (development)
- **Config file:** `_datos/iSync.iax`
- **Auto-discovery:** Enabled by default
- **Max peers:** 3 (configurable)

### iControl Integration
New configuration keys added to iControl:
- `isync_enabled`: Enable/disable iSync integration
- `isync_auto_discover`: Use automatic peer discovery
- `isync_peer_urls`: Manual peer URLs (comma-separated)

## Data Synchronization

### What Gets Synced
- Configuration records containing `_id` in their structure
- Paths matching pattern: `config._id.*`
- Records with `_id` in field values

### Sync Process
1. **Detection:** Changes to sync-eligible paths trigger sync
2. **Encryption:** Data is encrypted before transmission
3. **Transmission:** Sent to all connected peers via SocketIO
4. **Merge:** CRDT algorithms resolve conflicts
5. **Application:** Merged data updates local database

### Example Sync Data Structure
```json
{
  "_encrypted": true,
  "source_node": "icontrol-1728123456",
  "source_type": "iControl",
  "timestamp": 1728123456.789,
  "data": {
    "config": {
      "user_preferences_id": {
        "id": "user_preferences_id",
        "key": "theme_setting",
        "value": "dark",
        "description": "User theme preference"
      }
    }
  }
}
```

## API Endpoints

### iSync Standalone
- `GET /` - Dashboard
- `GET /peers` - Peer management
- `GET /config` - Configuration
- `POST /connect_peer` - Connect to peer
- `POST /sync_now` - Force sync
- `GET /api/stats` - Status API

### iControl Integration
- `GET /isync` - iSync dashboard
- `POST /isync/toggle` - Enable/disable iSync
- `POST /isync/sync_now` - Force sync
- `GET /isync/config` - Configure iSync
- `GET /api/isync/status` - iSync status API

## Peer Discovery

### Automatic Discovery
Fetches peer list from `https://tech.eus/isyncpeers.json`:
```json
[
  {
    "name": "Example Peer 1",
    "url": "https://peer1.example.com:5342",
    "description": "Production peer",
    "location": "US East",
    "verified": true
  },
  {
    "name": "Example Peer 2", 
    "url": "https://peer2.example.com:5342",
    "description": "Backup peer",
    "location": "EU West",
    "verified": false
  }
]
```

### Manual Configuration
- Add peer URLs directly in configuration
- Format: `https://hostname:port`
- Supports up to 3 peers
- Can be used as backup to auto-discovery

## Security Considerations

### ✅ What's Protected
- All synchronized data is encrypted
- Encryption keys are stored locally
- Peer authentication via handshake
- HTTPS recommended for peer connections

### ⚠️ What's Not Protected
- Peer existence/connectivity is visible
- Sync metadata (timestamps, node IDs)
- Network-level traffic analysis possible

### 🔑 Key Management
- Keys are generated automatically
- Base64 encoded for portability
- Must be shared manually between trusted peers
- No automatic key exchange

## Troubleshooting

### Common Issues

1. **"No peers connected"**
   - Check peer URLs are accessible
   - Verify firewall settings
   - Test auto-discovery service

2. **"Sync failed"**
   - Ensure encryption keys match
   - Check peer is running iSync
   - Verify network connectivity

3. **"Data not syncing"**
   - Confirm data matches `config._id.*` pattern
   - Check if iSync is enabled
   - Verify peer connections active

### Debug Mode
Start applications with `--dev` flag for verbose logging:
```bash
python main.py --dev
```

### Logs
Monitor console output for:
- Connection status
- Sync operations
- Error messages
- Peer discovery results

## Architecture Diagram

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   iControl A    │    │   iControl B    │    │   iControl C    │
│                 │    │                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │iSync Client │ │    │ │iSync Client │ │    │ │iSync Client │ │
│ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          │      SocketIO        │         SocketIO     │
          │                      │                      │
    ┌─────▼─────┐          ┌─────▼─────┐          ┌─────▼─────┐
    │ iSync A   │◄────────►│ iSync B   │◄────────►│ iSync C   │
    │ :5342     │  Mesh    │ :5342     │  Network │ :5342     │
    └───────────┘  Sync    └───────────┘          └───────────┘
         ▲                       ▲                       ▲
         │                       │                       │
         ▼                       ▼                       ▼
    ┌───────────┐          ┌───────────┐          ┌───────────┐
    │ CRDT      │          │ CRDT      │          │ CRDT      │
    │ Encrypted │          │ Encrypted │          │ Encrypted │
    │ Data      │          │ Data      │          │ Data      │
    └───────────┘          └───────────┘          └───────────┘
```

## Future Enhancements

### Planned Features
- [ ] Automatic key rotation
- [ ] Peer reputation system
- [ ] Advanced conflict resolution strategies
- [ ] Web UI for standalone iSync
- [ ] Backup/restore functionality
- [ ] Performance metrics and monitoring

### Integration Possibilities
- [ ] Integration with iAvisos for announcement sync
- [ ] Calendar synchronization across nodes
- [ ] User preference sync
- [ ] Device inventory synchronization

## Contributing

When contributing to iSync:

1. Maintain backward compatibility with existing iControl data
2. Follow the `config._id.*` pattern for new sync-enabled features
3. Test both standalone and integrated modes
4. Ensure encryption/decryption works across different platforms
5. Update documentation for new sync patterns

## License

iSync is part of the iControl project and follows the same licensing terms.
