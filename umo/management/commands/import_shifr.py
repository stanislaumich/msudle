from django.core.management.base import BaseCommand
from umo.models import Shifr


class Command(BaseCommand):
    help = 'Импорт шифров специальностей из CSV-файла (разделитель ";")'

    def add_arguments(self, parser):
        parser.add_argument('filepath', type=str, help='Путь к файлу, например e:\\s.txt')

    def handle(self, *args, **options):
        filepath = options['filepath']
        created = 0
        updated = 0
        skipped = 0

        with open(filepath, encoding='cp1251') as f:
            lines = f.readlines()

        # Пропускаем заголовок
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue

            parts = line.split(';')
            if len(parts) < 3:
                self.stdout.write(self.style.WARNING(f'Пропущена строка (неверный формат): {line}'))
                skipped += 1
                continue

            code = parts[0].strip()
            name = parts[1].strip()
            qualification = parts[2].strip()

            obj, is_new = Shifr.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'qualification': qualification,
                }
            )
            if is_new:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Импорт завершён. Создано: {created}, обновлено: {updated}, пропущено: {skipped}'
        ))