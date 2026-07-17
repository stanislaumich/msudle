from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from course.models import Course, CourseUserPermission, CourseGroupPermission, CourseGroupStudent


def index(request):
    """Лендинг — доступен всем: гостям, студентам, сотрудникам."""
    return render(request, 'main/index.html')


def home(request):
    """Домашняя страница для сотрудников."""
    return render(request, 'main/home.html')


def student_home(request):
    """Домашняя страница для студентов."""
    return render(request, 'main/student_home.html')


@login_required
def dashboard(request):
    """Личный кабинет — список курсов с правами пользователя."""
    user = request.user

    # Студенты — показываем курсы, на которые подписана их группа
    if hasattr(user, 'fio'):
        # Собираем курсы через подписку группы
        student_courses = Course.objects.filter(
            group_students__group_id=user.group_id
        ).select_related('subject__department__faculty').distinct()

        course_data = []
        for course in student_courses:
            course_data.append({
                'id': course.id,
                'full_name': course.full_name,
                'department': course.subject.department.full_name,
                'permission': 'Просмотр',
            })

        return render(request, 'main/dashboard.html', {
            'course_data': course_data,
            'is_student': True,
        })

    # Собираем права пользователя на курсы
    # Персональные права
    user_perms = {
        up.course_id: up.get_permission_display()
        for up in CourseUserPermission.objects.filter(user=user)
    }
    # Права через группы
    group_perms = {}
    user_group_ids = list(user.groups.values_list('id', flat=True))
    if user_group_ids:
        for gp in CourseGroupPermission.objects.filter(group_id__in=user_group_ids):
            gp_display = gp.get_permission_display()
            # Групповые права не перезаписывают персональные
            if gp.course_id not in user_perms:
                course_id = gp.course_id
                if course_id not in group_perms or _perm_weight(gp_display) > _perm_weight(group_perms[course_id]):
                    group_perms[course_id] = gp_display

    # Объединяем права
    all_perms = {**group_perms, **user_perms}

    # Получаем все курсы с правами
    course_ids = list(all_perms.keys())
    courses = Course.objects.filter(id__in=course_ids).select_related('subject__department__faculty')

    # Сортируем: сначала курсы, где права выше
    def sort_key(c):
        p = all_perms.get(c.id, '')
        return -_perm_weight(p), c.short_name

    courses = sorted(courses, key=sort_key)

    # Собираем данные для шаблона
    course_data = []
    for course in courses:
        perm = all_perms.get(course.id, 'Нет прав')
        course_data.append({
            'id': course.id,
            'full_name': course.full_name,
            'department': course.subject.department.full_name,
            'permission': perm,
        })

    return render(request, 'main/dashboard.html', {
        'course_data': course_data,
    })


def _perm_weight(perm_display):
    """Вес прав для сортировки (чем выше, тем приоритетнее)."""
    weights = {
        'Полный доступ': 4,
        'Создание и удаление': 3,
        'Редактирование': 2,
        'Только просмотр': 1,
    }
    return weights.get(perm_display, 0)

