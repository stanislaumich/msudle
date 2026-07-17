from django.core.management.base import BaseCommand
from course.models import CourseGroupStudent
from students.models import Student
from chat.models import ChatRoom


class Command(BaseCommand):
    help = 'Создаёт ChatRoom для всех существующих пар (курс, студент)'

    def handle(self, *args, **options):
        created_total = 0
        skipped_total = 0

        # Получаем все пары (course_id, group_id) из CourseGroupStudent
        pairs = list(CourseGroupStudent.objects.values_list('course_id', 'group_id').distinct())

        # Строим отображение group_id → список student_id
        student_by_group = {}
        for student in Student.objects.values('id', 'group_id'):
            gid = student['group_id']
            if gid:
                student_by_group.setdefault(gid, []).append(student['id'])

        # Строим множество (course_id, student_id) для get_or_create
        seen = set()
        for course_id, group_id in pairs:
            for student_id in student_by_group.get(group_id, []):
                key = (course_id, student_id)
                if key in seen:
                    continue
                seen.add(key)
                room, created = ChatRoom.objects.get_or_create(
                    course_id=course_id,
                    student_id=student_id,
                )
                if created:
                    created_total += 1
                else:
                    skipped_total += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Готово: создано {created_total} комнат, '
                f'пропущено (уже существовало) {skipped_total}.'
            )
        )
