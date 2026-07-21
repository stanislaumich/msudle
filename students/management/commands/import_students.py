"""
Management command для импорта студентов из CSV-файла.

Формат CSV (разделитель ;):
    фамилия;имя;отчество;факультет;номер_группы;номер_зачетки

Логика:
    1. Собираем уникальные номера групп (исключая '0', '', '1')
    2. Создаём/находим факультеты по названиям из CSV
    3. Создаём группы в StudentGroup с привязкой к факультету
    4. Создаём студентов с привязкой к группам

Использование:
    python manage.py import_students
"""
import csv
from django.core.management.base import BaseCommand
from students.models import StudentGroup, Student
from structure.models import Faculty, University
from accounts.views import generate_login, translit


# Маппинг первой цифры номера группы → название факультета (из CSV)
# и короткий код факультета
FACULTY_MAP = {
    '1': 'Факультет иностранных языков',
    '2': 'Историко-филологический факультет',
    '3': 'Факультет педагогики и психологии детства',
    '4': 'Факультет начального и музыкального образования',
    '5': 'Факультет математики и естествознания',
    '6': 'Факультет физического воспитания',
    '7': 'Факультет экономики и права',
}


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

        # Шаг 0: создаём/находим факультеты
        self.stdout.write('=== Сопоставление факультетов ===')
        faculty_cache = {}  # название факультета → Faculty объект
        # Получаем или создаём университет по умолчанию (МГУ)
        university, _ = University.objects.get_or_create(
            full_name='Московский государственный университет имени М.В. Ломоносова',
        )

        for digit, fac_name in sorted(FACULTY_MAP.items()):
            fac, created = Faculty.objects.get_or_create(
                full_name=fac_name,
                defaults={'university': university},
            )
            faculty_cache[fac_name] = fac
            if created:
                self.stdout.write(f'  Создан факультет: {fac_name}')
            else:
                self.stdout.write(f'  Найден факультет: {fac_name} (id={fac.id})')

        # Читаем CSV
        with open(path, encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            rows = list(reader)

        self.stdout.write(f'\nВсего строк в CSV: {len(rows)}')

        # Шаг 1: собираем уникальные номера групп с привязкой к факультету
        group_info = {}  # group_number -> {'faculty_name': ..., 'faculty': ...}
        valid_data = []
        skipped = 0
        for row in rows:
            if len(row) < 6:
                skipped += 1
                continue
            last_name, first_name, middle_name, faculty_name, group_num, record_book = row
            last_name = last_name.strip()
            first_name = first_name.strip()
            middle_name = middle_name.strip()
            faculty_name = faculty_name.strip()
            group_num = group_num.strip()
            record_book = record_book.strip()

            # Исключаем некорректные номера групп
            if group_num in ('', '0', '1'):
                skipped += 1
                continue

            # Определяем факультет по первой цифре номера группы
            first_digit = group_num[0]
            fac_name_from_digit = FACULTY_MAP.get(first_digit)
            if fac_name_from_digit:
                group_info[group_num] = {
                    'faculty_name': fac_name_from_digit,
                    'faculty': faculty_cache.get(fac_name_from_digit),
                }

            fio = f'{last_name} {first_name} {middle_name}'
            valid_data.append({
                'fio': fio,
                'group_number': group_num,
                'record_book': record_book,
            })

        self.stdout.write(f'Пропущено строк (без группы): {skipped}')
        self.stdout.write(f'Уникальных групп: {len(group_info)}')
        self.stdout.write(f'Студентов для импорта: {len(valid_data)}')

        # Шаг 2: создаём/обновляем группы с привязкой к факультету
        self.stdout.write('\n=== Создание/обновление групп ===')
        existing_groups = set(
            StudentGroup.objects.values_list('group_number', flat=True)
        )
        groups_to_create = set(group_info.keys()) - existing_groups

        group_map = {}
        for gn in groups_to_create:
            info = group_info.get(gn, {})
            fac = info.get('faculty')
            group = StudentGroup.objects.create(
                group_number=gn,
                faculty=fac,
            )
            group_map[gn] = group
            self.stdout.write(f'  Создана группа: {gn} (факультет: {fac.full_name if fac else "—"})')

        # Для уже существующих групп — обновляем факультет, если не задан
        updated_faculty = 0
        for g in StudentGroup.objects.filter(group_number__in=group_info.keys()):
            group_map[g.group_number] = g
            info = group_info.get(g.group_number, {})
            fac = info.get('faculty')
            if fac and g.faculty_id is None:
                g.faculty = fac
                g.save()
                updated_faculty += 1

        self.stdout.write(f'Создано новых групп: {len(groups_to_create)}')
        self.stdout.write(f'Обновлён факультет у существующих групп: {updated_faculty}')

        # Шаг 3: создаём студентов
        self.stdout.write('\n=== Импорт студентов ===')
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

            # Проверяем, нет ли уже студента с таким же ФИО в этой группе
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
            f'\nИмпорт завершён: создано {created}, обновлено {updated} студентов'
        ))
        self.stdout.write(f'Всего студентов в БД: {Student.objects.count()}')
        self.stdout.write(f'Всего групп в БД: {StudentGroup.objects.count()}')