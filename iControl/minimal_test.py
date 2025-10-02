print("Start")
print("Creating database...")

import sys
sys.path.append("..")

from iaxshared.iax_db import SimpleJSONDB

print("Creating instance...")
db = SimpleJSONDB("_datos/test.json")
print("Done!")
