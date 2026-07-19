import os

base = 's:\\Django\\msudle\\students\\migrations'
to_delete = [
    '0005_alter_student_id.py',
    '0006_alter_student_id.py',
]

for f in to_delete:
    path = os.path.join(base, f)
    if os.path.exists(path):
        os.remove(path)
        print(f'Deleted: {f}')

# Also delete __pycache__ for these
cache_dir = os.path.join(base, '__pycache__')
if os.path.exists(cache_dir):
    for f in os.listdir(cache_dir):
        if f.startswith(('0005_alter_student_id', '0006_alter_student_id')):
            os.remove(os.path.join(cache_dir, f))
            print(f'Deleted cache: {f}')

print('Done')