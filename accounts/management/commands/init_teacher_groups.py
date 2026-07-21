"""Создание начальных групп преподавателей."""
from django.core.management.base import BaseCommand
from accounts.models import TeacherGroup


class Command(BaseCommand):
    def handle(self, *args, **options):
        names = ['Преподаватели', 'Деканы', 'Ректорат', 'УМО', 'Заведующий кафедрой']
        for name in names:
            g, created = TeacherGroup.objects.get_or_create(name=name)
            if created:
                self.stdout.write(self.style.SUCCESS(f'  Создана группа: {name}'))
            else:
                self.stdout.write(f'  Уже существует: {name}')
        self.stdout.write(self.style.SUCCESS('Готово.'))