import os

# Assumption: the environment variable is always set
db_host = os.environ["DB_HOST"]

# Assumption: the list always has at least one element
items = get_items()
first = items[0]
