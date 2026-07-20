import csv
from django.core.management.base import BaseCommand
from umo.models import Shifr


class Command(BaseCommand):
    help = 'Импорт шифров из CSV-файла (code, name, qualification)'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Путь к CSV-файлу')

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        created = 0
        updated = 0

        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row['code'].strip()
                name = row.get('name', '').strip() or None
                qualification = row.get('qualification', '').strip() or None

                # Пытаемся найти существующий по code
                shifr, is_new = Shifr.objects.update_or_create(
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
            f'Импорт завершён: создано {created}, обновлено {updated}'
        ))