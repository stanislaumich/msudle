"""Management command: перенумерация факультетов по первым цифрам групп и авто-заполнение group_numbers."""
from django.core.management.base import BaseCommand
from django.db import connection
from structure.models import Faculty
from students.models import StudentGroup


class Command(BaseCommand):
    help = 'Renumber faculties so ID matches first digits of their groups, and fill group_numbers field.'

    def handle(self, *args, **options):
        groups = StudentGroup.objects.select_related('faculty').all().order_by('group_number')

        if not groups.exists():
            self.stdout.write(self.style.WARNING('Нет групп. Нечего перенумеровывать.'))
            return

        # Шаг 1: собираем маппинг {faculty_id: set of first_digits}
        faculty_digits = {}  # {faculty.id: set(str_digit)}
        faculty_groups = {}  # {faculty.id: [group_numbers]}
        for g in groups:
            fid = g.faculty_id
            if not fid:
                continue
            gnum = str(g.group_number).strip()
            if not gnum:
                continue
            first_digit = gnum[0]  # первая цифра
            faculty_digits.setdefault(fid, set()).add(first_digit)
            faculty_groups.setdefault(fid, []).append(gnum)

        if not faculty_digits:
            self.stdout.write(self.style.WARNING('Нет групп с привязанным факультетом.'))
            return

        # Шаг 2: для факультета с несколькими первыми цифрами — берём самую частую
        faculty_new_id = {}  # {old_id: new_id}
        for fid, digits in faculty_digits.items():
            # Считаем частоту
            counts = {}
            for gnum in faculty_groups.get(fid, []):
                d = str(gnum)[0]
                counts[d] = counts.get(d, 0) + 1
            best_digit = max(counts, key=counts.get)
            new_id = int(best_digit)
            faculty_new_id[fid] = new_id

        # Проверка конфликтов
        used_new_ids = {}
        for old_id, new_id in faculty_new_id.items():
            if new_id in used_new_ids:
                self.stdout.write(self.style.ERROR(
                    f'Конфликт: факультеты {used_new_ids[new_id]} и {old_id} претендуют на ID {new_id}. '
                    f'Проверьте номера групп вручную.'
                ))
                return
            used_new_ids[new_id] = old_id

        # Шаг 3: выполняем перенумерацию (меняем id в самой таблице + все FK)
        with connection.cursor() as cursor:
            # SQLite: временно отключаем проверку FK
            cursor.execute("PRAGMA foreign_keys = OFF;")

            try:
                for old_id, new_id in faculty_new_id.items():
                    if old_id == new_id:
                        continue

                    faculty = Faculty.objects.get(id=old_id)
                    self.stdout.write(f'  Факультет {old_id} «{faculty.full_name}» → ID {new_id}')

                    # Обновляем FK в StudentGroup
                    cursor.execute(
                        "UPDATE students_studentgroup SET faculty_id = %s WHERE faculty_id = %s",
                        [new_id, old_id]
                    )
                    # Обновляем FK в Shifr (umo_shifr)
                    cursor.execute(
                        "UPDATE umo_shifr SET faculty_id = %s WHERE faculty_id = %s",
                        [new_id, old_id]
                    )
                    # Обновляем FK в Department
                    cursor.execute(
                        "UPDATE structure_department SET faculty_id = %s WHERE faculty_id = %s",
                        [new_id, old_id]
                    )
                    # Обновляем ID в самой таблице faculty (обход FK)
                    # Сначала создаём запись с новым ID
                    cursor.execute(
                        "INSERT INTO structure_faculty (id, university_id, full_name, short_name, identifier, dean_id, group_numbers) "
                        "SELECT %s, university_id, full_name, short_name, identifier, dean_id, group_numbers "
                        "FROM structure_faculty WHERE id = %s",
                        [new_id, old_id]
                    )
                    # Удаляем старую
                    cursor.execute(
                        "DELETE FROM structure_faculty WHERE id = %s",
                        [old_id]
                    )
            finally:
                cursor.execute("PRAGMA foreign_keys = ON;")

        # Шаг 4: авто-заполнение group_numbers
        # Перечитываем группы с обновлёнными FK
        groups_updated = StudentGroup.objects.select_related('faculty').all().order_by('group_number')
        fac_digits_map = {}  # {faculty_id: set(str)}
        for g in groups_updated:
            fid = g.faculty_id
            if not fid:
                continue
            gnum = str(g.group_number).strip()
            if not gnum:
                continue
            fac_digits_map.setdefault(fid, set()).add(gnum[0])

        for fid, digits in fac_digits_map.items():
            sorted_digits = sorted(digits)
            gn_str = ','.join(sorted_digits)
            Faculty.objects.filter(id=fid).update(group_numbers=gn_str)

        self.stdout.write(self.style.SUCCESS(
            f'Готово. Перенумеровано факультетов: {len(faculty_new_id)}. '
            f'Заполнены номера групп.'
        ))