#!/usr/bin/env python3

print("Testing database initialization...")

try:
    from iaxshared.iax_db import SimpleJSONDB
    print("✓ Import successful")
    
    print("Creating database instance...")
    db = SimpleJSONDB('test_db.json')
    print("✓ Database created")
    
    print("Creating table...")
    db.create_table('test')
    print("✓ Table created")
    
    print("Inserting record...")
    record_id = db.insert('test', {'name': 'Test User', 'age': 25})
    print(f"✓ Record inserted with ID: {record_id}")
    
    print("Finding record by ID...")
    record = db.find_by_id('test', record_id)
    print(f"✓ Found record: {record}")
    
    print("All tests passed!")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
