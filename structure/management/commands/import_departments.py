"""
Перенос кафедр из старой БД (db.sqlite3) в текущую с правильной привязкой к факультетам.

Использование:
    python manage.py import_departments
"""
import sqlite3
from django.core.management.base import BaseCommand
from structure.models import Department, Faculty


class Command(BaseCommand):
    help = 'Перенос кафедр из db.sqlite3 в текущую БД'

    SOURCE_DB = 'db.sqlite3'

    def handle(self, *args, **options):
        # Читаем старую БД
        src = sqlite3.connect(self.SOURCE_DB)
        src.row_factory = sqlite3.Row
        cur = src.cursor()

        # Получаем факультеты из старой БД
        old_faculties = {}
        cur.execute('SELECT id, full_name, short_name FROM structure_faculty')
        for row in cur.fetchall():
            old_faculties[row['id']] = {
                'full_name': row['full_name'],
                'short_name': row['short_name'],
            }

        self.stdout.write('=== Факультеты из старой БД ===')
        for fid, info in sorted(old_faculties.items()):
            self.stdout.write(f'  id={fid}: {info["full_name"]} ({info["short_name"]})')

        # Получаем кафедры из старой БД
        cur.execute('SELECT id, full_name, short_name, faculty_id, identifier FROM structure_department')
        old_departments = cur.fetchall()

        self.stdout.write(f'\nКафедр в старой БД: {len(old_departments)}')

        # Строим маппинг: название факультета → Faculty объект в текущей БД
        current_faculties = {}
        for fac in Faculty.objects.all():
            current_faculties[fac.full_name] = fac

        self.stdout.write('\n=== Сопоставление факультетов ===')

        # Ручной маппинг для факультетов с опечатками в старой БД
        FACULTY_NAME_FIXES = {
            'Факультет физического воспистания': 'Факультет физического воспитания',
        }

        faculty_map = {}  # old_faculty_id → текущий Faculty объект
        for fid, info in old_faculties.items():
            full = info['full_name']
            # Пробуем исправить опечатку
            fixed = FACULTY_NAME_FIXES.get(full, full)
            fac = current_faculties.get(fixed)
            if fac:
                faculty_map[fid] = fac
                if full != fixed:
                    self.stdout.write(f'  {full} → {fixed} (исправлена опечатка) → id={fac.id}')
                else:
                    self.stdout.write(f'  {full} → найден в текущей БД (id={fac.id})')
            else:
                self.stdout.write(self.style.WARNING(f'  {full} → НЕ НАЙДЕН в текущей БД!'))

        # Перенос кафедр
        self.stdout.write('\n=== Перенос кафедр ===')
        created = 0
        updated = 0

        for row in old_departments:
            full_name = row['full_name']
            short_name = row['short_name']
            old_faculty_id = row['faculty_id']
            identifier = row['identifier']

            fac = faculty_map.get(old_faculty_id)
            if not fac:
                self.stdout.write(self.style.WARNING(
                    f'  ПРОПУЩЕНО: {full_name} (нет факультета для old_id={old_faculty_id})'
                ))
                continue

            # Проверяем, существует ли уже такая кафедра
            dept, created_flag = Department.objects.get_or_create(
                full_name=full_name,
                defaults={
                    'short_name': short_name,
                    'faculty': fac,
                    'identifier': identifier,
                },
            )
            if created_flag:
                created += 1
                self.stdout.write(f'  Создана: {full_name} → факультет {fac.full_name}')
            else:
                # Обновляем привязку к факультету и остальные поля
                updated_flag = False
                if dept.faculty_id != fac.id:
                    dept.faculty = fac
                    updated_flag = True
                if dept.identifier != identifier:
                    dept.identifier = identifier
                    updated_flag = True
                if dept.short_name != short_name:
                    dept.short_name = short_name
                    updated_flag = True
                if updated_flag:
                    dept.save()
                    updated += 1
                    self.stdout.write(f'  Обновлена: {full_name} (факультет: {fac.full_name})')
                else:
                    self.stdout.write(f'  Уже существует: {full_name}')

        src.close()

        self.stdout.write(self.style.SUCCESS(
            f'\nПеренос завершён: создано {created}, обновлено {updated} кафедр'
        ))
        self.stdout.write(f'Всего кафедр в БД: {Department.objects.count()}')