"""
Management command для импорта студентов из CSV-файла.

Формат CSV (разделитель ;):
    фамилия;имя;отчество;факультет;номер_группы;номер_зачетки

Логика:
    1. Собираем уникальные номера групп (исключая '0', '', '1')
    2. Создаём группы в StudentGroup
    3. Создаём студентов с привязкой к группам

Использование:
    python manage.py import_students
"""
import csv
from django.core.management.base import BaseCommand
from students.models import StudentGroup, Student
from accounts.views import generate_login, translit


class Command(BaseCommand):
    help = 'Импорт студентов из students.csv'

    CSV_PATH = 'students.csv'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            default=self.CSV_PATH,
            help='Путь к CSV-файлу (по умолчанию students.csv)',
        )

    def handle(self, *args, **options):
        path = options['path']

        # Читаем CSV
        with open(path, encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            rows = list(reader)

        self.stdout.write(f'Всего строк в CSV: {len(rows)}')

        # Шаг 1: собираем уникальные номера групп
        group_numbers = set()
        valid_data = []
        skipped = 0
        for row in rows:
            if len(row) < 6:
                skipped += 1
                continue
            last_name, first_name, middle_name, faculty, group_num, record_book = row
            last_name = last_name.strip()
            first_name = first_name.strip()
            middle_name = middle_name.strip()
            group_num = group_num.strip()
            record_book = record_book.strip()

            # Исключаем некорректные номера групп
            if group_num in ('', '0', '1'):
                skipped += 1
                continue

            group_numbers.add(group_num)
            fio = f'{last_name} {first_name} {middle_name}'
            valid_data.append({
                'fio': fio,
                'group_number': group_num,
                'record_book': record_book,
            })

        self.stdout.write(f'Пропущено строк (без группы): {skipped}')
        self.stdout.write(f'Уникальных групп: {len(group_numbers)}')
        self.stdout.write(f'Студентов для импорта: {len(valid_data)}')

        # Шаг 2: создаём группы
        existing_groups = set(
            StudentGroup.objects.values_list('group_number', flat=True)
        )
        groups_to_create = group_numbers - existing_groups

        group_map = {}
        for gn in groups_to_create:
            group = StudentGroup.objects.create(
                group_number=gn,
                subgroup_number=None,
            )
            group_map[gn] = group
            self.stdout.write(f'  Создана группа: {gn}')
        # Добавляем уже существующие
        for g in StudentGroup.objects.filter(group_number__in=group_numbers):
            group_map[g.group_number] = g

        self.stdout.write(f'Создано новых групп: {len(groups_to_create)}')

        # Шаг 3: создаём студентов
        created = 0
        updated = 0
        existing_logins = set(Student.objects.values_list('login', flat=True))

        for data in valid_data:
            fio = data['fio']
            group_num = data['group_number']
            record_book = data['record_book']
            group = group_map.get(group_num)

            if not group:
                continue

            # Генерируем логин по ФИО
            login = generate_login(fio)
            if not login:
                # Фолбэк: берём первые буквы + случайное число
                import random
                parts = fio.split()
                initials = ''.join(p[0] for p in parts if p).lower()
                initials = translit(initials)
                login = f'{initials}{random.randint(1000, 9999)}'

            # Проверяем уникальность логина
            counter = 0
            base_login = login
            while login in existing_logins:
                counter += 1
                login = f'{base_login}{counter}'
                if counter > 99:
                    import random
                    login = f'{base_login}{random.randint(10000, 99999)}'

            existing_logins.add(login)

            # Проверяем, нет ли уже студента с таким же номером зачётки или ФИО в этой группе
            student = Student.objects.filter(
                fio=fio,
                group=group,
            ).first()

            if student:
                # Обновляем существующего
                student.login = login
                student.record_book_number = record_book
                student.set_password('12345')
                student.save()
                updated += 1
            else:
                student = Student.objects.create(
                    fio=fio,
                    login=login,
                    group=group,
                    record_book_number=record_book,
                )
                student.set_password('12345')
                student.save()
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Импорт завершён: создано {created}, обновлено {updated} студентов'
        ))