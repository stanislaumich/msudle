import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, user='postgres', password='postgres', dbname='postgres')
conn.autocommit = True
cur = conn.cursor()

# Check if database exists
cur.execute("SELECT 1 FROM pg_database WHERE datname='msudle'")
exists = cur.fetchone()
print('DB msudle exists:', exists is not None)

if not exists:
    cur.execute("CREATE DATABASE msudle ENCODING 'UTF8'")
    print('Database msudle created successfully')
else:
    print('Database msudle already exists')

cur.close()
conn.close()