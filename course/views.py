import os

from django.db import models as django_models
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from collections import OrderedDict

from .models import Course, CourseUserPermission, CourseGroupPermission, CourseSection, CourseTopic, LearningUnit, CourseGroupStudent, StudentAnswer


def _get_user_permission(user, course):
    """
    Возвращает наивысшее право пользователя на курс.
    Порядок: full_access > create_delete > edit > view.
    Если прав нет — None.
    """
    perm_weight = {
        'full_access': 4,
        'create_delete': 3,
        'edit': 2,
        'view': 1,
    }
    best = None
    best_weight = 0

    # Персональные права
    try:
        up = CourseUserPermission.objects.get(course=course, user=user)
        w = perm_weight.get(up.permission, 0)
        if w > best_weight:
            best_weight = w
            best = up.permission
    except CourseUserPermission.DoesNotExist:
        pass

    # Групповые права
    user_group_ids = list(user.groups.values_list('id', flat=True))
    if user_group_ids:
        for gp in CourseGroupPermission.objects.filter(course=course, group_id__in=user_group_ids):
            w = perm_weight.get(gp.permission, 0)
            if w > best_weight:
                best_weight = w
                best = gp.permission

    return best


@login_required
def course_edit(request, course_id):
    """Страница редактирования курса: разделы, темы, единицы."""
    course = get_object_or_404(
        Course.objects.prefetch_related(
            'sections__topics__units',
            'sections__direct_units',
        ),
        id=course_id
    )

    # Проверяем права: edit, create_delete или full_access
    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        # Нет прав на редактирование
        return redirect('dashboard')

    sections = course.sections.all()
    enrolled_groups = course.group_students.select_related('group').all()
    enrolled_group_ids = set(eg.group_id for eg in enrolled_groups)

    from students.models import StudentGroup
    all_groups = StudentGroup.objects.all().order_by('group_number', 'subgroup_number')

    context = {
        'course': course,
        'sections': sections,
        'user_perm': user_perm,
        'enrolled_groups': enrolled_groups,
        'enrolled_group_ids': enrolled_group_ids,
        'all_groups': all_groups,
    }
    return render(request, 'course/edit.html', context)


@login_required
@require_POST
def section_delete(request, section_id):
    """Удаление раздела курса."""
    section = get_object_or_404(CourseSection, id=section_id)
    course = section.course

    # Проверяем права: нужны edit или выше
    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на удаление раздела.')
        return redirect('dashboard')

    # Удаляем файлы единиц раздела (темы + прямые единицы)
    units = LearningUnit.objects.filter(
        django_models.Q(topic__section=section) | django_models.Q(section=section)
    )
    for unit in units:
        if unit.file and os.path.isfile(unit.file.path):
            os.remove(unit.file.path)
    section.delete()
    messages.success(request, f'Раздел «{section.name}» успешно удалён.')
    return redirect('course:course_edit', course_id=course.id)


@login_required
def course_grades(request, course_id):
    """Таблица успеваемости: группы → студенты → контрольные единицы."""
    course = get_object_or_404(Course, id=course_id)

    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на просмотр успеваемости.')
        return redirect('dashboard')

    # Подписанные группы
    enrolled = CourseGroupStudent.objects.filter(course=course).select_related('group')
    groups_data = []
    all_control_units = []

    # Собираем контрольные единицы курса (только из тем и прямые)
    control_units_qs = LearningUnit.objects.filter(
        django_models.Q(topic__section__course=course) | django_models.Q(section__course=course),
        content_type='control',
    ).order_by('order', 'id')
    all_control_units = list(control_units_qs)

    for eg in enrolled:
        group = eg.group
        students = group.students.all().order_by('fio')

        # Собираем ответы для всех студентов группы на все контрольные единицы
        student_ids = [s.id for s in students]
        answers_qs = StudentAnswer.objects.filter(
            student_id__in=student_ids,
            learning_unit__in=all_control_units,
        ).select_related('learning_unit')

        # Строим матрицу: {student_id: {unit_id: answer}}
        answer_matrix = {}
        for ans in answers_qs:
            answer_matrix.setdefault(ans.student_id, {})[ans.learning_unit_id] = ans

        student_rows = []
        group_total_scores = []  # для вычисления среднего балла по группе
        for student in students:
            cells = []
            student_total_score = 0
            for unit in all_control_units:
                answer = answer_matrix.get(student.id, {}).get(unit.id)
                # Суммируем баллы только проверенных ответов с числовым score
                if answer and answer.checked and answer.score is not None:
                    student_total_score += answer.score
                cells.append({
                    'unit': unit,
                    'answer': answer,
                })
            student_rows.append({
                'student': student,
                'cells': cells,
                'total_score': student_total_score,
            })
            group_total_scores.append(student_total_score)

        # Средний балл по группе и общая сумма
        group_sum_score = sum(group_total_scores)
        group_avg_score = round(group_sum_score / len(group_total_scores), 1) if group_total_scores else 0

        groups_data.append({
            'group': group,
            'student_rows': student_rows,
            'control_units': all_control_units,
            'group_sum_score': group_sum_score,
            'group_avg_score': group_avg_score,
        })

    context = {
        'course': course,
        'groups_data': groups_data,
        'all_control_units': all_control_units,
    }
    return render(request, 'course/grades.html', context)


@login_required
def student_grades(request, course_id):
    """Таблица успеваемости для студента: одна строка — он сам."""
    user = request.user
    if not hasattr(user, 'fio'):
        messages.error(request, 'Только студенты могут просматривать свою успеваемость.')
        return redirect('dashboard')

    course = get_object_or_404(Course, id=course_id)

    # Проверяем подписку
    if not user.group_id:
        messages.error(request, 'Вы не прикреплены к группе.')
        return redirect('index')
    if not CourseGroupStudent.objects.filter(course=course, group_id=user.group_id).exists():
        messages.error(request, 'Вы не подписаны на этот курс.')
        return redirect('index')

    # Собираем контрольные единицы курса
    control_units_qs = LearningUnit.objects.filter(
        django_models.Q(topic__section__course=course) | django_models.Q(section__course=course),
        content_type='control',
    ).order_by('order', 'id')
    all_control_units = list(control_units_qs)

    # Ответы студента
    answers_qs = StudentAnswer.objects.filter(
        student=user,
        learning_unit__in=all_control_units,
    ).select_related('learning_unit')
    answer_map = {a.learning_unit_id: a for a in answers_qs}

    # Строим одну строку
    cells = []
    total_score = 0
    for unit in all_control_units:
        answer = answer_map.get(unit.id)
        if answer and answer.checked and answer.score is not None:
            total_score += answer.score
        cells.append({
            'unit': unit,
            'answer': answer,
        })

    student_row = {
        'student': user,
        'cells': cells,
        'total_score': total_score,
    }

    context = {
        'course': course,
        'all_control_units': all_control_units,
        'student_row': student_row,
        'is_student': True,
    }
    return render(request, 'course/student_grades.html', context)


@login_required
def student_answer(request, unit_id):
    """Ответ студента на контрольную единицу."""
    user = request.user
    if not hasattr(user, 'fio'):
        messages.error(request, 'Только студенты могут отправлять ответы.')
        return redirect('dashboard')

    unit = get_object_or_404(LearningUnit, id=unit_id, content_type='control')

    # Определяем курс
    if unit.topic:
        course = unit.topic.section.course
    else:
        course = unit.section.course

    # Проверяем подписку
    if not CourseGroupStudent.objects.filter(course=course, group_id=user.group_id).exists():
        messages.error(request, 'Вы не подписаны на этот курс.')
        return redirect('index')

    if request.method == 'POST':
        # Получаем или создаём существующий ответ
        answer, created = StudentAnswer.objects.get_or_create(
            student=user,
            learning_unit=unit,
        )

        # Если загружен новый файл — удаляем старый
        uploaded_file = request.FILES.get('answer_file')
        if uploaded_file:
            if answer.answer_file and os.path.isfile(answer.answer_file.path):
                os.remove(answer.answer_file.path)
            answer.answer_file = uploaded_file

        # Текстовый ответ
        answer_text = request.POST.get('answer_text', '').strip()
        if answer_text:
            answer.answer_text = answer_text

        # Если был изменён — сбрасываем проверку
        answer.checked = False
        answer.score = None
        answer.passed = None
        answer.checked_at = None
        answer.checked_modified_at = None

        answer.save()
        msg = 'Ответ отправлен.' if created else 'Ответ обновлён.'
        messages.success(request, msg)

    return redirect('course:course_view', course_id=course.id)


@login_required
def course_view(request, course_id):
    """Страница просмотра курса: разделы, темы, единицы (для администратора и студента)."""
    course = get_object_or_404(
        Course.objects.prefetch_related(
            'sections__topics__units',
            'sections__direct_units',
        ),
        id=course_id
    )

    user = request.user

    # Определяем, студент это или сотрудник
    is_student = hasattr(user, 'fio')

    if is_student:
        # Студент: проверяем, подписана ли его группа на курс
        if user.group_id:
            is_enrolled = CourseGroupStudent.objects.filter(
                course=course, group_id=user.group_id
            ).exists()
        else:
            is_enrolled = False

        if not is_enrolled:
            messages.error(request, 'Вы не подписаны на этот курс.')
            return redirect('index')
    else:
        # Сотрудник/админ: проверяем права (view и выше)
        user_perm = _get_user_permission(user, course)
        allowed_perms = {'view', 'edit', 'create_delete', 'full_access'}
        if user_perm not in allowed_perms:
            messages.error(request, 'У вас нет прав на просмотр этого курса.')
            return redirect('dashboard')

    sections = course.sections.all()

    # Для студента: собираем ответы на контрольные единицы этого курса
    answer_map = {}
    if is_student:
        # Собираем ID всех контрольных единиц курса
        control_unit_ids = LearningUnit.objects.filter(
            django_models.Q(topic__section__course=course) | django_models.Q(section__course=course),
            content_type='control',
        ).values_list('id', flat=True)
        answers = StudentAnswer.objects.filter(
            student=user, learning_unit_id__in=control_unit_ids
        )
        answer_map = {a.learning_unit_id: a for a in answers}

    context = {
        'course': course,
        'sections': sections,
        'is_student': is_student,
        'answer_map': answer_map,
    }
    return render(request, 'course/view.html', context)


@login_required
@require_POST
def course_enroll_groups(request, course_id):
    """Подписка групп студентов на курс."""
    course = get_object_or_404(Course, id=course_id)

    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на подписку групп.')
        return redirect('dashboard')

    group_ids = request.POST.getlist('group_ids', [])
    if not group_ids:
        messages.error(request, 'Не выбрана ни одна группа.')
        return redirect('course:course_edit', course_id=course.id)

    from students.models import StudentGroup
    enrolled = 0
    for gid in group_ids:
        try:
            gid = int(gid)
        except (ValueError, TypeError):
            continue
        group = StudentGroup.objects.filter(id=gid).first()
        if group and not CourseGroupStudent.objects.filter(course=course, group=group).exists():
            CourseGroupStudent.objects.create(course=course, group=group)
            enrolled += 1

    if enrolled:
        messages.success(request, f'На курс подписано групп: {enrolled}.')
    else:
        messages.warning(request, 'Все выбранные группы уже подписаны на курс.')

    return redirect('course:course_edit', course_id=course.id)


@login_required
@require_POST
def course_unenroll_group(request, gs_id):
    """Отписка группы студентов от курса."""
    gs = get_object_or_404(CourseGroupStudent, id=gs_id)
    course = gs.course

    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на отписку групп.')
        return redirect('dashboard')

    group_name = str(gs.group)
    gs.delete()
    messages.success(request, f'Группа «{group_name}» отписана от курса.')
    return redirect('course:course_edit', course_id=course.id)


@login_required
def section_edit(request, section_id):
    """Редактирование раздела."""
    section = get_object_or_404(CourseSection, id=section_id)
    course = section.course

    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на редактирование раздела.')
        return redirect('dashboard')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Название раздела обязательно.')
            return redirect('course:course_edit', course_id=course.id)

        section.name = name
        try:
            order = int(request.POST.get('order', str(section.order)))
            if order < 1:
                order = 1
        except (ValueError, TypeError):
            order = section.order
        section.order = order
        section.save()
        messages.success(request, f'Раздел «{section.name}» обновлён.')

    return redirect('course:course_edit', course_id=course.id)


@login_required
@require_POST
def topic_toggle_visibility(request, topic_id):
    """Переключение видимости темы для студентов."""
    topic = get_object_or_404(CourseTopic, id=topic_id)
    course = topic.section.course

    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на изменение видимости темы.')
        return redirect('dashboard')

    topic.visible = not topic.visible
    topic.save(update_fields=['visible'])
    state = 'видима' if topic.visible else 'скрыта'
    messages.success(request, f'Тема «{topic.content}» теперь {state} для студентов.')
    return redirect('course:course_edit', course_id=course.id)


@login_required
@require_POST
def unit_toggle_visibility(request, unit_id):
    """Переключение видимости единицы для студентов."""
    unit = get_object_or_404(LearningUnit, id=unit_id)

    if unit.topic:
        course = unit.topic.section.course
    else:
        course = unit.section.course

    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на изменение видимости единицы.')
        return redirect('dashboard')

    unit.visible = not unit.visible
    unit.save(update_fields=['visible'])
    state = 'видима' if unit.visible else 'скрыта'
    messages.success(request, f'Единица «{unit.title}» теперь {state} для студентов.')
    return redirect('course:course_edit', course_id=course.id)


@login_required
def topic_edit(request, topic_id):
    """Редактирование темы."""
    topic = get_object_or_404(CourseTopic, id=topic_id)
    course = topic.section.course

    # Проверяем права
    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на редактирование темы.')
        return redirect('dashboard')

    if request.method == 'POST':
        entity_title = request.POST.get('entity_title', '').strip()
        content = request.POST.get('content', '').strip()

        if not entity_title or not content:
            messages.error(request, 'Название сущности и содержание обязательны.')
            return redirect('course:course_edit', course_id=course.id)

        topic.entity_title = entity_title
        topic.content = content

        # Обновление порядка
        try:
            order = int(request.POST.get('order', str(topic.order)))
            if order < 1:
                order = 1
        except (ValueError, TypeError):
            order = topic.order
        topic.order = order

        topic.save()
        messages.success(request, f'Тема «{topic.content}» обновлена.')

    return redirect('course:course_edit', course_id=course.id)


@login_required
def unit_edit(request, unit_id):
    """Редактирование единицы обучения."""
    unit = get_object_or_404(LearningUnit, id=unit_id)

    # Определяем курс
    if unit.topic:
        course = unit.topic.section.course
    else:
        course = unit.section.course

    # Проверяем права
    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на редактирование единицы.')
        return redirect('dashboard')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        if not title:
            messages.error(request, 'Название единицы обязательно.')
            return redirect('course:course_edit', course_id=course.id)

        unit.title = title

        # Обновление content_type (из формы добавления — content_type, из формы редактирования — edit_content_type)
        new_content_type = request.POST.get('content_type') or request.POST.get('edit_content_type', unit.content_type)
        if new_content_type in dict(LearningUnit.CONTENT_TYPE_CHOICES):
            unit.content_type = new_content_type
            if new_content_type != 'control':
                unit.grading_type = None
            else:
                grading = request.POST.get('grading_type', '') or request.POST.get('edit_grading_type', '')
                if grading in dict(LearningUnit.GRADING_TYPE_CHOICES):
                    unit.grading_type = grading
                elif not unit.grading_type:
                    unit.grading_type = None
                # max_score — только для контрольных
                try:
                    max_score = int(request.POST.get('max_score', '') or request.POST.get('edit_max_score', ''))
                    if max_score >= 1:
                        unit.max_score = max_score
                except (ValueError, TypeError):
                    pass
        else:
            unit.grading_type = None

        # Обновление ссылки
        link = request.POST.get('link', '').strip()
        unit.link = link if link else None

        # Обновление файла
        uploaded_file = request.FILES.get('file')
        if uploaded_file:
            # Удаляем старый файл если был
            if unit.file and os.path.isfile(unit.file.path):
                os.remove(unit.file.path)
            unit.file = uploaded_file
            # Ссылку сбрасываем, т.к. загружен новый файл
            unit.link = None

        # Обновление порядка
        try:
            order = int(request.POST.get('order', str(unit.order)))
            if order < 1:
                order = 1
        except (ValueError, TypeError):
            order = unit.order
        unit.order = order

        unit.save()
        messages.success(request, f'Единица «{unit.title}» обновлена.')

    return redirect('course:course_edit', course_id=course.id)


def _add_unit(request, course, topic=None, section=None):
    """
    Внутренняя функция добавления единицы обучения.
    Принимает либо topic, либо section.
    """
    title = request.POST.get('title', '').strip()
    link = request.POST.get('link', '').strip()
    uploaded_file = request.FILES.get('file')

    if not title:
        messages.error(request, 'Название единицы обязательно.')
        return redirect('course:course_edit', course_id=course.id)

    # Вычисляем следующий порядковый номер
    if topic:
        # Единица внутри темы: считаем единицы этой темы
        last_unit = topic.units.order_by('-order').first()
    else:
        # Единица напрямую в разделе: считаем прямые единицы раздела
        last_unit = section.direct_units.order_by('-order').first()
    next_order = (last_unit.order + 1) if last_unit else 1

    # content_type из формы
    content_type = request.POST.get('content_type', 'lecture')
    if content_type not in dict(LearningUnit.CONTENT_TYPE_CHOICES):
        content_type = 'lecture'

    # grading_type — только для контрольных
    grading_type = None
    max_score = 10
    if content_type == 'control':
        gtype = request.POST.get('grading_type', '')
        if gtype in dict(LearningUnit.GRADING_TYPE_CHOICES):
            grading_type = gtype
        try:
            max_score = int(request.POST.get('max_score', '10'))
            if max_score < 1:
                max_score = 10
        except (ValueError, TypeError):
            max_score = 10

    LearningUnit.objects.create(
        topic=topic,
        section=section,
        title=title,
        content_type=content_type,
        grading_type=grading_type,
        max_score=max_score,
        file=uploaded_file if uploaded_file else None,
        link=link if link else None,
        order=next_order,
    )
    messages.success(request, f'Единица «{title}» добавлена.')


@login_required
def unit_add_to_topic(request, topic_id):
    """Добавление единицы обучения в тему."""
    topic = get_object_or_404(CourseTopic, id=topic_id)
    course = topic.section.course

    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на добавление единицы.')
        return redirect('dashboard')

    if request.method == 'POST':
        _add_unit(request, course, topic=topic)

    return redirect('course:course_edit', course_id=course.id)


@login_required
def unit_add_to_section(request, section_id):
    """Добавление единицы обучения напрямую в раздел."""
    section = get_object_or_404(CourseSection, id=section_id)
    course = section.course

    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на добавление единицы.')
        return redirect('dashboard')

    if request.method == 'POST':
        _add_unit(request, course, section=section)

    return redirect('course:course_edit', course_id=course.id)


@login_required
def topic_add(request, section_id):
    """Добавление темы в раздел."""
    section = get_object_or_404(CourseSection, id=section_id)
    course = section.course

    # Проверяем права
    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на добавление темы.')
        return redirect('dashboard')

    if request.method == 'POST':
        entity_title = request.POST.get('entity_title', '').strip()
        content = request.POST.get('content', '').strip()

        if not entity_title or not content:
            messages.error(request, 'Название сущности и содержание обязательны.')
            return redirect('course:course_edit', course_id=course.id)

        # Вычисляем следующий порядковый номер
        last_topic = section.topics.order_by('-order').first()
        next_order = (last_topic.order + 1) if last_topic else 1

        CourseTopic.objects.create(
            section=section,
            entity_title=entity_title,
            content=content,
            order=next_order,
        )
        messages.success(request, f'Тема «{content}» добавлена в раздел «{section.name}».')

    return redirect('course:course_edit', course_id=course.id)


@login_required
@require_POST
def unit_delete(request, unit_id):
    """Удаление единицы обучения."""
    unit = get_object_or_404(LearningUnit, id=unit_id)

    # Определяем курс: единица может быть привязана к теме или напрямую к разделу
    if unit.topic:
        course = unit.topic.section.course
    else:
        course = unit.section.course

    # Проверяем права
    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на удаление единицы обучения.')
        return redirect('dashboard')

    title = unit.title
    # Удаляем файл с диска, если он есть
    if unit.file and os.path.isfile(unit.file.path):
        os.remove(unit.file.path)
    unit.delete()
    messages.success(request, f'Единица «{title}» успешно удалена.')
    return redirect('course:course_edit', course_id=course.id)


@login_required
@require_POST
def section_toggle_visibility(request, section_id):
    """Переключение видимости раздела для студентов."""
    section = get_object_or_404(CourseSection, id=section_id)
    course = section.course

    # Проверяем права
    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на изменение видимости раздела.')
        return redirect('dashboard')

    section.visible = not section.visible
    section.save(update_fields=['visible'])

    state = 'видим' if section.visible else 'скрыт'
    messages.success(request, f'Раздел «{section.name}» теперь {state} для студентов.')
    return redirect('course:course_edit', course_id=course.id)


@login_required
@require_POST
def topic_delete(request, topic_id):
    """Удаление темы с выбором судьбы её единиц: удалить или перенести в раздел."""
    topic = get_object_or_404(CourseTopic, id=topic_id)
    section = topic.section
    course = section.course

    # Проверяем права
    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на удаление темы.')
        return redirect('dashboard')

    units_action = request.POST.get('units_action', 'delete')

    if units_action == 'move_to_section':
        # Переносим все единицы темы в раздел напрямую
        count = topic.units.count()
        topic.units.update(section=section, topic=None)
        topic.delete()
        messages.success(
            request,
            f'Тема «{topic.content}» удалена. {count} единиц(ы) перенесены в раздел «{section.name}».'
        )
    else:
        # Удаляем тему вместе с единицами
        count = topic.units.count()
        topic.delete()
        messages.success(
            request,
            f'Тема «{topic.content}» удалена вместе с {count} единицами.'
        )

    return redirect('course:course_edit', course_id=course.id)