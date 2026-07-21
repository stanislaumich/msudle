"""Management command: расстановка формы обучения по второй цифре номера группы.
1 = дневная (daytime), 2 = заочная (correspondence).
"""
from django.core.management.base import BaseCommand
from students.models import StudentGroup


class Command(BaseCommand):
    help = 'Assign education_form based on second digit of group number.'

    def handle(self, *args, **options):
        daytime = 0
        correspondence = 0
        skipped = 0

        for g in StudentGroup.objects.all():
            n = str(g.group_number)
            if len(n) < 2:
                skipped += 1
                continue
            d2 = n[1]
            if d2 == '1':
                g.education_form = 'daytime'
                daytime += 1
            elif d2 == '2':
                g.education_form = 'correspondence'
                correspondence += 1
            else:
                skipped += 1
                continue
            g.save(update_fields=['education_form'])

        self.stdout.write(self.style.SUCCESS(
            f'Дневная: {daytime}, Заочная: {correspondence}, Пропущено: {skipped}'
        ))