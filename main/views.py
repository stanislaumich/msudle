from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db import models as django_models
from course.models import Course, CourseUserPermission, CourseGroupPermission, CourseGroupStudent


def index(request):
    """Лендинг — доступен всем: гостям, студентам, сотрудникам."""
    return render(request, 'main/index.html')


def home(request):
    """Домашняя страница для сотрудников — сводная успеваемость и объявления."""
    user = request.user
    if hasattr(user, 'fio'):
        return redirect('student_home')

    from course.models import CourseAnnouncement, AnnouncementDismiss, StudentAnswer

    user_perm_ids = set(
        CourseUserPermission.objects.filter(user=user).values_list('course_id', flat=True)
    )
    user_group_ids = list(user.groups.values_list('id', flat=True))
    group_perm_ids = set()
    if user_group_ids:
        group_perm_ids = set(
            CourseGroupPermission.objects.filter(group_id__in=user_group_ids).values_list('course_id', flat=True)
        )
    all_course_ids = user_perm_ids | group_perm_ids

    dismissed_ids = set(
        AnnouncementDismiss.objects.filter(user=user).values_list('announcement_id', flat=True)
    )
    announcements = CourseAnnouncement.objects.filter(
        course_id__in=all_course_ids
    ).exclude(id__in=dismissed_ids).select_related('course', 'author').order_by('-created_at')[:20]

    # Подсчёт непроверенных ответов по курсам
    from django.db.models import Q
    unchecked_counts = {}
    if all_course_ids:
        unchecked_qs = (
            StudentAnswer.objects
            .filter(
                checked=False,
                learning_unit__topic__section__course_id__in=all_course_ids
            )
            .values('learning_unit__topic__section__course_id')
            .annotate(cnt=django_models.Count('id'))
        )
        for row in unchecked_qs:
            cid = row['learning_unit__topic__section__course_id']
            unchecked_counts[cid] = row['cnt']
        unchecked_direct = (
            StudentAnswer.objects
            .filter(
                checked=False,
                learning_unit__section__course_id__in=all_course_ids
            )
            .values('learning_unit__section__course_id')
            .annotate(cnt=django_models.Count('id'))
        )
        for row in unchecked_direct:
            cid = row['learning_unit__section__course_id']
            unchecked_counts[cid] = unchecked_counts.get(cid, 0) + row['cnt']

    # Формируем список курсов с непроверенными ответами
    unchecked_courses = []
    if unchecked_counts:
        courses_map = {
            c.id: c
            for c in Course.objects.filter(id__in=unchecked_counts.keys()).select_related('subject__department__faculty')
        }
        for cid, cnt in unchecked_counts.items():
            course = courses_map.get(cid)
            if course:
                unchecked_courses.append({
                    'id': course.id,
                    'full_name': course.full_name,
                    'department': course.subject.department.full_name,
                    'unchecked_count': cnt,
                })
        # Сортируем: сначала больше непроверенных, потом по имени
        unchecked_courses.sort(key=lambda x: (-x['unchecked_count'], x['full_name']))

    # Сбор непрочитанных сообщений от студентов
    from chat.models import ChatRoom, ChatMessage
    unread_chats = []
    if all_course_ids:
        chat_rooms = ChatRoom.objects.filter(
            course_id__in=all_course_ids,
        ).select_related('course', 'student')

        for room in chat_rooms:
            unread_messages = list(
                room.messages.filter(
                    sender_student__isnull=False,  # от студента
                    is_read=False,
                ).select_related('sender_student').order_by('created_at')
            )
            if unread_messages:
                unread_chats.append({
                    'room_id': room.id,
                    'course': room.course,
                    'course_id': room.course_id,
                    'student': room.student,
                    'student_id': room.student_id,
                    'messages': unread_messages,
                    'unread_count': len(unread_messages),
                })

    return render(request, 'main/home.html', {
        'announcements': announcements,
        'unchecked_courses': unchecked_courses,
        'unread_chats': unread_chats,
    })


def student_home(request):
    """Домашняя страница для студентов — сводная успеваемость по всем курсам."""
    user = request.user
    if not hasattr(user, 'fio'):
        return render(request, 'main/student_home.html')

    from django.db import models as django_models
    from course.models import LearningUnit, StudentAnswer, CourseAnnouncement, AnnouncementDismiss

    enrolled = CourseGroupStudent.objects.filter(
        group_id=user.group_id
    ).select_related('course__subject__department__faculty')

    student_course_ids = list(enrolled.values_list('course_id', flat=True))

    dismissed_ids = set(
        AnnouncementDismiss.objects.filter(student=user).values_list('announcement_id', flat=True)
    )
    announcements = CourseAnnouncement.objects.filter(
        course_id__in=student_course_ids
    ).exclude(id__in=dismissed_ids).select_related('course', 'author').order_by('-created_at')[:20]

    courses_data = []
    for eg in enrolled:
        course = eg.course
        control_units = list(LearningUnit.objects.filter(
            django_models.Q(topic__section__course=course) | django_models.Q(section__course=course),
            content_type='control',
        ).order_by('order', 'id'))

        if not control_units:
            continue

        answers = StudentAnswer.objects.filter(
            student=user,
            learning_unit__in=control_units,
        ).select_related('learning_unit')
        answer_map = {a.learning_unit_id: a for a in answers}

        cells = []
        total_score = 0
        for unit in control_units:
            answer = answer_map.get(unit.id)
            if answer and answer.checked and answer.score is not None:
                total_score += answer.score
            cells.append({
                'unit': unit,
                'answer': answer,
            })

        units_count = len(control_units)
        avg_score = round(total_score / units_count, 1) if units_count > 0 else 0

        # Собираем преподавателей с правами редактирования
        from course.models import CourseUserPermission, CourseGroupPermission
        teacher_ids = set()
        # Персональные права
        for perm in CourseUserPermission.objects.filter(
            course=course,
            permission__in=('edit', 'create_delete', 'full_access'),
        ).select_related('user'):
            teacher_ids.add(perm.user)
        # Групповые права
        group_perms = CourseGroupPermission.objects.filter(
            course=course,
            permission__in=('edit', 'create_delete', 'full_access'),
        ).select_related('group')
        for gp in group_perms:
            for u in gp.group.user_set.all():
                teacher_ids.add(u)
        # Формируем список ФИО
        teachers_list = []
        for t in teacher_ids:
            name = t.get_full_name() or t.get_username()
            teachers_list.append({'id': t.id, 'name': name})
        teachers_list.sort(key=lambda x: x['name'])

        courses_data.append({
            'course': course,
            'control_units': control_units,
            'cells': cells,
            'total_score': total_score,
            'avg_score': avg_score,
            'teachers': teachers_list,
        })

    # Сбор непрочитанных сообщений из чатов
    from chat.models import ChatRoom, ChatMessage
    unread_chats = []
    if student_course_ids:
        chat_rooms = ChatRoom.objects.filter(
            course_id__in=student_course_ids,
            student=user,
        ).select_related('course')

        for room in chat_rooms:
            unread_messages = list(
                room.messages.filter(
                    sender_user__isnull=False,   # от преподавателя
                    is_read=False,
                ).select_related('sender_user').order_by('created_at')
            )
            if unread_messages:
                unread_chats.append({
                    'room_id': room.id,
                    'course': room.course,
                    'course_id': room.course_id,
                    'student_id': user.id,
                    'messages': unread_messages,
                    'unread_count': len(unread_messages),
                })

    return render(request, 'main/student_home.html', {
        'courses_data': courses_data,
        'announcements': announcements,
        'unread_chats': unread_chats,
    })


@login_required
def dashboard(request):
    """Личный кабинет — список курсов с правами пользователя."""
    user = request.user

    if hasattr(user, 'fio'):
        student_courses = Course.objects.filter(
            group_students__group_id=user.group_id
        ).select_related('subject__department__faculty').distinct()

        from course.models import CourseAnnouncement, AnnouncementDismiss
        student_course_ids = list(student_courses.values_list('id', flat=True))
        dismissed_ids = set(
            AnnouncementDismiss.objects.filter(student=user).values_list('announcement_id', flat=True)
        )
        announcements = CourseAnnouncement.objects.filter(
            course_id__in=student_course_ids
        ).exclude(id__in=dismissed_ids).select_related('course', 'author').order_by('-created_at')[:20]

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
            'announcements': announcements,
        })

    user_perms = {
        up.course_id: up.get_permission_display()
        for up in CourseUserPermission.objects.filter(user=user)
    }
    group_perms = {}
    user_group_ids = list(user.groups.values_list('id', flat=True))
    if user_group_ids:
        for gp in CourseGroupPermission.objects.filter(group_id__in=user_group_ids):
            gp_display = gp.get_permission_display()
            if gp.course_id not in user_perms:
                course_id = gp.course_id
                if course_id not in group_perms or _perm_weight(gp_display) > _perm_weight(group_perms[course_id]):
                    group_perms[course_id] = gp_display

    all_perms = {**group_perms, **user_perms}
    course_ids = list(all_perms.keys())
    courses = Course.objects.filter(id__in=course_ids).select_related('subject__department__faculty')

    from course.models import CourseAnnouncement, AnnouncementDismiss, StudentAnswer
    dismissed_ids = set(
        AnnouncementDismiss.objects.filter(user=user).values_list('announcement_id', flat=True)
    )
    announcements = CourseAnnouncement.objects.filter(
        course_id__in=course_ids
    ).exclude(id__in=dismissed_ids).select_related('course', 'author').order_by('-created_at')[:20]

    # Подсчёт непроверенных ответов по каждому курсу (одним запросом)
    from django.db.models import Q
    unchecked_counts = {}
    if course_ids:
        unchecked_qs = (
            StudentAnswer.objects
            .filter(
                checked=False,
                learning_unit__topic__section__course_id__in=course_ids
            )
            .values('learning_unit__topic__section__course_id')
            .annotate(cnt=django_models.Count('id'))
        )
        for row in unchecked_qs:
            cid = row['learning_unit__topic__section__course_id']
            unchecked_counts[cid] = row['cnt']
        # Также учитываем единицы, привязанные напрямую к разделу (без темы)
        unchecked_direct = (
            StudentAnswer.objects
            .filter(
                checked=False,
                learning_unit__section__course_id__in=course_ids
            )
            .values('learning_unit__section__course_id')
            .annotate(cnt=django_models.Count('id'))
        )
        for row in unchecked_direct:
            cid = row['learning_unit__section__course_id']
            unchecked_counts[cid] = unchecked_counts.get(cid, 0) + row['cnt']

    def sort_key(c):
        p = all_perms.get(c.id, '')
        return -_perm_weight(p), c.short_name

    courses = sorted(courses, key=sort_key)

    course_data = []
    for course in courses:
        perm = all_perms.get(course.id, 'Нет прав')
        course_data.append({
            'id': course.id,
            'full_name': course.full_name,
            'department': course.subject.department.full_name,
            'permission': perm,
            'unchecked_count': unchecked_counts.get(course.id, 0),
        })

    return render(request, 'main/dashboard.html', {
        'course_data': course_data,
        'announcements': announcements,
    })


def _perm_weight(perm_display):
    weights = {
        'Полный доступ': 4,
        'Создание и удаление': 3,
        'Редактирование': 2,
        'Только просмотр': 1,
    }
    return weights.get(perm_display, 0)