from django.core.management.base import BaseCommand
from students.models import Student


class Command(BaseCommand):
    help = 'Установить всем студентам пароль = login.lower()'

    def handle(self, *args, **options):
        students = Student.objects.all()
        updated = 0

        for student in students:
            new_password = student.login.lower()
            student.set_password(new_password)
            student.save(update_fields=['password'])
            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Пароли установлены для {updated} студентов (пароль = логин в нижнем регистре)'
        ))