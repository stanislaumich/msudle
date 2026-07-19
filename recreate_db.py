import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, user='postgres', password='postgres', dbname='postgres')
conn.autocommit = True
cur = conn.cursor()

# Drop existing connections to msudle
cur.execute("""
    SELECT pg_terminate_backend(pg_stat_activity.pid)
    FROM pg_stat_activity
    WHERE pg_stat_activity.datname = 'msudle'
    AND pid <> pg_backend_pid()
""")

# Drop and recreate
cur.execute('DROP DATABASE IF EXISTS msudle')
cur.execute("CREATE DATABASE msudle ENCODING 'UTF8'")
print('DB msudle recreated successfully')

cur.close()
conn.close()