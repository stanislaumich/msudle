import sys
import os
import io

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Set environment for SQLite
os.environ['DB_ENGINE'] = 'sqlite3'
os.environ['DB_NAME'] = 'db.sqlite3'

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'msudle.settings')
django.setup()

from django.core.management import call_command

with open('data_dump.json', 'w', encoding='utf-8') as f:
    # Temporarily redirect stdout
    original_stdout = sys.stdout
    sys.stdout = f
    call_command(
        'dumpdata',
        '--natural-foreign',
        '--natural-primary',
        '-e', 'contenttypes',
        '-e', 'auth.Permission',
        '--indent', '2',
    )
    sys.stdout = original_stdout

print('Dump created: data_dump.json', file=original_stdout)