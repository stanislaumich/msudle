import os

from django.db import models as django_models
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Group
from django.views.decorators.http import require_POST
from collections import OrderedDict

from .models import Course, CourseUserPermission, CourseGroupPermission, CourseSection, CourseTopic, LearningUnit, CourseGroupStudent, StudentAnswer, CourseAnnouncement
from students.models import Student


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
def course_create(request):
    """Создание нового курса."""
    # Только администраторы (is_staff) могут создавать курсы
    if not request.user.is_staff:
        messages.error(request, 'Только администраторы могут создавать курсы.')
        return redirect('dashboard')

    from subject.models import Subject

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        short_name = request.POST.get('short_name', '').strip()
        identifier = request.POST.get('identifier', '').strip() or None
        subject_id = request.POST.get('subject', '').strip()

        if not full_name or not short_name or not subject_id:
            messages.error(request, 'Полное наименование, краткое наименование и дисциплина обязательны.')
            return redirect('course:course_create')

        try:
            subject = Subject.objects.get(id=int(subject_id))
        except (Subject.DoesNotExist, ValueError, TypeError):
            messages.error(request, 'Выбранная дисциплина не существует.')
            return redirect('course:course_create')

        # Проверка уникальности identifier
        if identifier and Course.objects.filter(identifier=identifier).exists():
            messages.error(request, f'Идентификатор «{identifier}» уже используется.')
            return redirect('course:course_create')

        course = Course.objects.create(
            subject=subject,
            full_name=full_name,
            short_name=short_name,
            identifier=identifier,
        )

        # Автоматически назначаем права (как в админке)
        _assign_default_permissions(request.user, course)
        _assign_default_sections(course)

        messages.success(request, f'Курс «{course.short_name}» успешно создан.')
        return redirect('course:course_edit', course_id=course.id)

    # GET — показываем форму
    subjects = Subject.objects.select_related('department__faculty').all().order_by('full_name')
    return render(request, 'course/create.html', {
        'subjects': subjects,
    })


def _assign_default_permissions(creator, course):
    """При создании курса: создателю — полный доступ, декану — просмотр, зав. кафедрой — просмотр."""
    # Создатель — полный доступ
    CourseUserPermission.objects.get_or_create(
        course=course,
        user=creator,
        defaults={'permission': 'full_access'},
    )
    # Декан факультета (через subject → department → faculty)
    department = course.subject.department
    faculty = department.faculty
    if faculty.dean:
        CourseUserPermission.objects.get_or_create(
            course=course,
            user=faculty.dean,
            defaults={'permission': 'view'},
        )
    # Заведующий кафедрой
    if department.head:
        CourseUserPermission.objects.get_or_create(
            course=course,
            user=department.head,
            defaults={'permission': 'view'},
        )
    # Группы УМО и Ректорат — просмотр
    for group_name in ('УМО', 'Ректорат'):
        try:
            group = Group.objects.get(name=group_name)
            CourseGroupPermission.objects.get_or_create(
                course=course,
                group=group,
                defaults={'permission': 'view'},
            )
        except Group.DoesNotExist:
            pass


def _assign_default_sections(course):
    """Добавляет разделы по умолчанию к новому курсу."""
    for i, name in enumerate(CourseSection.DEFAULT_SECTIONS, start=1):
        CourseSection.objects.get_or_create(
            course=course,
            name=name,
            defaults={'order': i},
        )


@login_required
@require_POST
def course_delete(request, course_id):
    """Удаление курса."""
    # Только администраторы (is_staff) могут удалять курсы
    if not request.user.is_staff:
        messages.error(request, 'Только администраторы могут удалять курсы.')
        return redirect('dashboard')

    course = get_object_or_404(Course, id=course_id)

    # Удаляем файлы всех единиц курса
    units = LearningUnit.objects.filter(
        django_models.Q(topic__section__course=course) | django_models.Q(section__course=course)
    )
    for unit in units:
        if unit.file and os.path.isfile(unit.file.path):
            os.remove(unit.file.path)

    # Удаляем файлы ответов студентов
    answers = StudentAnswer.objects.filter(
        django_models.Q(learning_unit__topic__section__course=course) |
        django_models.Q(learning_unit__section__course=course)
    )
    for answer in answers:
        if answer.answer_file and os.path.isfile(answer.answer_file.path):
            os.remove(answer.answer_file.path)

    course_name = course.short_name
    course.delete()
    messages.success(request, f'Курс «{course_name}» успешно удалён.')
    return redirect('dashboard')


@login_required
@require_POST
def check_answer(request, answer_id):
    """Сохранение оценки (проверка) ответа студента преподавателем."""
    answer = get_object_or_404(StudentAnswer.objects.select_related(
        'learning_unit__topic__section__course',
        'learning_unit__section__course',
    ), id=answer_id)

    # Определяем курс
    if answer.learning_unit.topic:
        course = answer.learning_unit.topic.section.course
    else:
        course = answer.learning_unit.section.course

    # Проверяем права
    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на проверку ответов.')
        return redirect('dashboard')

    unit = answer.learning_unit

    # Определяем тип оценки
    grading_type = unit.grading_type or 'score_100'

    if grading_type == 'pass_fail':
        passed_raw = request.POST.get('passed', '')
        if passed_raw == 'true':
            answer.passed = True
            answer.score = 1  # условный балл
        elif passed_raw == 'false':
            answer.passed = False
            answer.score = 0
        else:
            messages.error(request, 'Укажите результат зачёта.')
            return redirect('course:course_grades', course_id=course.id)
    else:
        # score_100
        try:
            score = int(request.POST.get('score', ''))
            max_score = unit.max_score or 100
            if score < 0 or score > max_score:
                messages.error(request, f'Балл должен быть от 0 до {max_score}.')
                return redirect('course:course_grades', course_id=course.id)
        except (ValueError, TypeError):
            messages.error(request, 'Введите числовой балл.')
            return redirect('course:course_grades', course_id=course.id)
        answer.score = score
        answer.passed = None

    from django.utils import timezone
    now = timezone.now()

    if answer.checked:
        # Обновление существующей проверки
        answer.checked_modified_at = now
    else:
        # Первая проверка
        answer.checked = True
        answer.checked_at = now

    # Сохраняем комментарий преподавателя
    comment = request.POST.get('comment', '').strip()
    if comment:
        answer.comment = comment
    else:
        answer.comment = None

    answer.save()

    student_name = answer.student.login
    messages.success(request, f'Оценка для «{student_name}» сохранена.')
    return redirect('course:course_grades', course_id=course.id)


@login_required
@require_POST
def check_answer_no_submission(request, course_id, student_id, unit_id):
    """Выставление оценки за задание, на которое студент не дал ответа.
    Создаёт запись StudentAnswer с датами ответа и проверки = сейчас."""
    course = get_object_or_404(Course, id=course_id)
    student = get_object_or_404(Student, id=student_id)
    unit = get_object_or_404(LearningUnit, id=unit_id, content_type='control')

    # Проверяем права
    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на проверку ответов.')
        return redirect('dashboard')

    from django.utils import timezone
    now = timezone.now()

    # Создаём или получаем ответ
    answer, created = StudentAnswer.objects.get_or_create(
        student=student,
        learning_unit=unit,
        defaults={
            'checked': True,
            'created_at': now,
            'modified_at': now,
            'checked_at': now,
            'checked_modified_at': now,
        },
    )

    # Если ответ уже существовал — обновляем даты
    if not created:
        answer.created_at = now
        answer.modified_at = now
        answer.checked = True
        answer.checked_at = now
        answer.checked_modified_at = now

    # Выставляем оценку
    grading_type = unit.grading_type or 'score_100'
    if grading_type == 'pass_fail':
        passed_raw = request.POST.get('passed', '')
        if passed_raw == 'true':
            answer.passed = True
            answer.score = 1
        elif passed_raw == 'false':
            answer.passed = False
            answer.score = 0
        else:
            messages.error(request, 'Укажите результат зачёта.')
            return redirect('course:course_grades', course_id=course.id)
    else:
        try:
            score = int(request.POST.get('score', ''))
            max_score = unit.max_score or 100
            if score < 0 or score > max_score:
                messages.error(request, f'Балл должен быть от 0 до {max_score}.')
                return redirect('course:course_grades', course_id=course.id)
        except (ValueError, TypeError):
            messages.error(request, 'Введите числовой балл.')
            return redirect('course:course_grades', course_id=course.id)
        answer.score = score
        answer.passed = None

    # Комментарий
    comment = request.POST.get('comment', '').strip()
    answer.comment = comment if comment else None

    answer.save()

    student_name = student.login
    messages.success(request, f'Оценка для «{student_name}» сохранена.')
    return redirect('course:course_grades', course_id=course.id)


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
            units_count = len(all_control_units)
            student_avg_score = round(student_total_score / units_count, 1) if units_count > 0 else 0
            student_rows.append({
                'student': student,
                'cells': cells,
                'total_score': student_total_score,
                'avg_score': student_avg_score,
            })
            group_total_scores.append(student_total_score)

        # Средний балл по группе и общая сумма
        group_sum_score = sum(group_total_scores)
        group_avg_score = round(group_sum_score / len(group_total_scores), 1) if group_total_scores else 0

        # Считаем количество непроверенных ответов в группе
        unchecked_count = 0
        for ans in answers_qs:
            if not ans.checked:
                unchecked_count += 1

        groups_data.append({
            'group': group,
            'student_rows': student_rows,
            'control_units': all_control_units,
            'group_sum_score': group_sum_score,
            'group_avg_score': group_avg_score,
            'unchecked_count': unchecked_count,
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

    units_count = len(all_control_units)
    student_avg = round(total_score / units_count, 1) if units_count > 0 else 0
    student_row = {
        'student': user,
        'cells': cells,
        'total_score': total_score,
        'avg_score': student_avg,
    }

    # Собираем преподавателей с правами редактирования
    teachers_list = []
    perms = CourseUserPermission.objects.filter(
        course=course,
        permission__in=('edit', 'create_delete', 'full_access'),
    ).select_related('user')
    teacher_ids = set()
    for p in perms:
        teacher_ids.add(p.user)
    group_perms = CourseGroupPermission.objects.filter(
        course=course,
        permission__in=('edit', 'create_delete', 'full_access'),
    ).select_related('group')
    for gp in group_perms:
        for u in gp.group.user_set.all():
            teacher_ids.add(u)
    for t in teacher_ids:
        name = t.get_full_name() or t.get_username()
        teachers_list.append({'id': t.id, 'name': name})
    teachers_list.sort(key=lambda x: x['name'])

    context = {
        'course': course,
        'all_control_units': all_control_units,
        'student_row': student_row,
        'is_student': True,
        'teachers': teachers_list,
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

        next_url = request.POST.get('next', '')
        if next_url:
            return redirect(next_url)
        return redirect('course:course_view', course_id=course.id)

    return redirect('course:course_view', course_id=course.id)


@login_required
def start_test(request, unit_id):
    """Прохождение теста студентом."""
    user = request.user
    if not hasattr(user, 'fio'):
        messages.error(request, 'Только студенты могут проходить тесты.')
        return redirect('dashboard')

    unit = get_object_or_404(LearningUnit.objects.select_related('test'), id=unit_id, content_type='control')
    if not unit.test:
        messages.error(request, 'К этому заданию не прикреплён тест.')
        return redirect('course:course_view', course_id=_get_course_for_unit(unit).id)

    course = _get_course_for_unit(unit)
    if not CourseGroupStudent.objects.filter(course=course, group_id=user.group_id).exists():
        messages.error(request, 'Вы не подписаны на этот курс.')
        return redirect('index')

    # Проверяем, не пройден ли тест
    from .models import StudentAnswer
    existing = StudentAnswer.objects.filter(student=user, learning_unit=unit).first()
    if existing and existing.checked:
        messages.warning(request, 'Вы уже прошли этот тест. Повторное прохождение невозможно.')
        return redirect('course:course_view', course_id=course.id)

    test = unit.test
    questions = list(test.questions.prefetch_related('choices').all())
    if not questions:
        messages.error(request, 'В тесте нет вопросов.')
        return redirect('course:course_view', course_id=course.id)

    max_score = unit.max_score or 10

    if request.method == 'POST':
        # Подсчёт баллов
        raw_score = 0
        total_possible = 0
        results = []
        for q in questions:
            total_possible += q.score
            choice_ids = request.POST.getlist(f'q_{q.id}')
            chosen_ids = set(int(c) for c in choice_ids if c.isdigit())
            correct_ids = set(q.choices.filter(is_correct=True).values_list('id', flat=True))
            is_correct = chosen_ids == correct_ids
            if is_correct:
                raw_score += q.score
            results.append({
                'question': q,
                'chosen_ids': chosen_ids,
                'is_correct': is_correct,
            })

        # Масштабируем балл к max_score единицы
        if total_possible > 0:
            scaled_score = round(raw_score * max_score / total_possible)
            # Не превышаем max_score
            if scaled_score > max_score:
                scaled_score = max_score
            if scaled_score < 0:
                scaled_score = 0
        else:
            scaled_score = 0

        from django.utils import timezone
        now = timezone.now()

        # Сохраняем ответ
        answer, created = StudentAnswer.objects.update_or_create(
            student=user,
            learning_unit=unit,
            defaults={
                'checked': True,
                'score': scaled_score,
                'passed': None,
                'checked_at': now,
                'checked_modified_at': now,
                'answer_text': f'Тест пройден: {raw_score}/{total_possible} баллов',
            },
        )

        return render(request, 'course/take_test.html', {
            'unit': unit,
            'test': test,
            'questions': questions,
            'results': results,
            'raw_score': raw_score,
            'total_possible': total_possible,
            'scaled_score': scaled_score,
            'max_score': max_score,
            'submitted': True,
            'course_id': course.id,
        })

    return render(request, 'course/take_test.html', {
        'unit': unit,
        'test': test,
        'questions': questions,
        'course_id': course.id,
    })


def _get_course_for_unit(unit):
    """Возвращает курс, к которому относится единица."""
    if unit.topic:
        return unit.topic.section.course
    return unit.section.course


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

    # ID объявлений, скрытых текущим пользователем (для персонального статуса)
    from .models import AnnouncementDismiss
    from students.models import Student
    if isinstance(user, Student):
        dismissed_ids = set(
            AnnouncementDismiss.objects.filter(student=user).values_list('announcement_id', flat=True)
        )
    else:
        dismissed_ids = set(
            AnnouncementDismiss.objects.filter(user=user).values_list('announcement_id', flat=True)
        )

    context = {
        'course': course,
        'sections': sections,
        'is_student': is_student,
        'answer_map': answer_map,
        'dismissed_announcement_ids': dismissed_ids,
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

        # Обновление test_id
        if new_content_type == 'control':
            test_id_raw = request.POST.get('test_id', '') or request.POST.get('edit_test_id', '')
            if test_id_raw:
                from testing.models import Test
                try:
                    if Test.objects.filter(id=int(test_id_raw)).exists():
                        unit.test_id = int(test_id_raw)
                except (ValueError, TypeError):
                    pass
            else:
                unit.test_id = None
        else:
            unit.test_id = None

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

    # test_id — только для контрольных
    test_id = None
    if content_type == 'control':
        test_id_raw = request.POST.get('test_id', '')
        if test_id_raw:
            from testing.models import Test
            try:
                if Test.objects.filter(id=int(test_id_raw)).exists():
                    test_id = int(test_id_raw)
            except (ValueError, TypeError):
                pass

    LearningUnit.objects.create(
        topic=topic,
        section=section,
        title=title,
        content_type=content_type,
        grading_type=grading_type,
        max_score=max_score,
        test_id=test_id,
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

    add_another = request.POST.get('add_another', '')
    if add_another:
        from django.urls import reverse
        from urllib.parse import urlencode
        last_title = request.POST.get('title', '').strip()
        last_content_type = request.POST.get('content_type', 'lecture').strip()
        last_grading_type = request.POST.get('grading_type', '').strip()
        last_max_score = request.POST.get('max_score', '10').strip()
        params = urlencode({
            'add_another': '1',
            'target_type': 'topic',
            'target_id': topic_id,
            'target_name': topic.content,
            'last_title': last_title,
            'content_type': last_content_type,
            'grading_type': last_grading_type,
            'max_score': last_max_score,
        })
        return redirect(f"{reverse('course:course_edit', args=[course.id])}?{params}")
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

    add_another = request.POST.get('add_another', '')
    if add_another:
        from django.urls import reverse
        from urllib.parse import urlencode
        last_title = request.POST.get('title', '').strip()
        last_content_type = request.POST.get('content_type', 'lecture').strip()
        last_grading_type = request.POST.get('grading_type', '').strip()
        last_max_score = request.POST.get('max_score', '10').strip()
        params = urlencode({
            'add_another': '1',
            'target_type': 'section',
            'target_id': section_id,
            'target_name': section.name,
            'last_title': last_title,
            'content_type': last_content_type,
            'grading_type': last_grading_type,
            'max_score': last_max_score,
        })
        return redirect(f"{reverse('course:course_edit', args=[course.id])}?{params}")
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
def announcement_create(request, course_id):
    """Создание объявления по курсу."""
    course = get_object_or_404(Course, id=course_id)

    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms and not request.user.is_staff:
        messages.error(request, 'У вас нет прав на создание объявлений.')
        return redirect('dashboard')

    text = request.POST.get('text', '').strip()
    if not text:
        messages.error(request, 'Введите текст объявления.')
        return redirect('course:course_grades', course_id=course.id)

    CourseAnnouncement.objects.create(
        course=course,
        author=request.user,
        text=text,
    )
    messages.success(request, 'Объявление опубликовано.')
    next_url = request.POST.get('next', '')
    if next_url:
        return redirect(next_url)
    return redirect('dashboard')


@login_required
@require_POST
def announcement_hide(request, announcement_id):
    """Персональное скрытие объявления (преподаватель или студент)."""
    announcement = get_object_or_404(CourseAnnouncement, id=announcement_id)
    course = announcement.course

    # Проверяем доступ (для преподавателя — права; для студента — подписка)
    user = request.user
    if hasattr(user, 'fio'):
        if not CourseGroupStudent.objects.filter(course=course, group_id=user.group_id).exists():
            messages.error(request, 'Вы не подписаны на этот курс.')
            return redirect('dashboard')
    else:
        user_perm = _get_user_permission(user, course)
        allowed_perms = {'edit', 'create_delete', 'full_access'}
        if user_perm not in allowed_perms and not user.is_staff:
            messages.error(request, 'У вас нет прав.')
            return redirect('dashboard')

    # Создаём персональную запись скрытия
    from .models import AnnouncementDismiss
    from students.models import Student
    if isinstance(user, Student):
        AnnouncementDismiss.objects.get_or_create(
            announcement=announcement,
            student=user,
        )
    else:
        AnnouncementDismiss.objects.get_or_create(
            announcement=announcement,
            user=user,
        )
    messages.success(request, 'Объявление скрыто.')
    next_url = request.POST.get('next', '')
    if next_url:
        return redirect(next_url)
    return redirect('dashboard')


@login_required
@require_POST
def announcement_dismiss(request, announcement_id):
    """Синоним announcement_hide (для совместимости URL)."""
    return announcement_hide(request, announcement_id)


@login_required
@require_POST
def announcement_restore(request, announcement_id):
    """Отмена скрытия объявления — удаляет персональный dismiss."""
    announcement = get_object_or_404(CourseAnnouncement, id=announcement_id)
    user = request.user

    from .models import AnnouncementDismiss
    from students.models import Student

    if isinstance(user, Student):
        AnnouncementDismiss.objects.filter(announcement=announcement, student=user).delete()
    else:
        AnnouncementDismiss.objects.filter(announcement=announcement, user=user).delete()

    messages.success(request, 'Объявление снова отображается.')
    next_url = request.POST.get('next', '')
    if next_url:
        return redirect(next_url)
    return redirect('dashboard')


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