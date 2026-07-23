import json
import os
import re
import urllib.parse

from django.db import models as django_models
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Group, User
from django.views.decorators.http import require_POST
from collections import OrderedDict

from .models import Course, CourseUserPermission, CourseGroupPermission, CourseSection, CourseTopic, LearningUnit, CourseGroupStudent, StudentAnswer, CourseAnnouncement
from students.models import Student


def _get_unit_course(unit):
    """Возвращает курс, к которому относится единица обучения, или None если не привязана."""
    if unit.topic:
        return unit.topic.section.course
    if unit.section:
        return unit.section.course
    return None


def _get_user_permission(user, course):
    """
    Возвращает наивысшее право пользователя на курс.
    Порядок: full_access > create_delete > edit > view.
    Если прав нет — None.
    """
    if course is None:
        return None

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
    all_groups = StudentGroup.objects.all().order_by('group_number')

    # Права преподавателей
    user_permissions = course.user_permissions.select_related('user').all()
    group_permissions = course.group_permissions.select_related('group').all()
    all_teachers = User.objects.filter(is_active=True, is_staff=True).order_by('last_name', 'first_name')
    all_teacher_groups = Group.objects.all().order_by('name')
    permission_choices = CourseUserPermission.PERMISSION_CHOICES

    context = {
        'course': course,
        'sections': sections,
        'user_perm': user_perm,
        'enrolled_groups': enrolled_groups,
        'enrolled_group_ids': enrolled_group_ids,
        'all_groups': all_groups,
        'user_permissions': user_permissions,
        'group_permissions': group_permissions,
        'all_teachers': all_teachers,
        'all_teacher_groups': all_teacher_groups,
        'permission_choices': permission_choices,
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
def step_by_step_export(request, unit_id):
    """Экспорт пошаговой единицы в JSON (только для преподавателей)."""
    user = request.user
    if hasattr(user, 'fio'):
        messages.error(request, 'Только преподаватели могут экспортировать пошаговые единицы.')
        return redirect('course:step_by_step_list')

    unit = get_object_or_404(
        LearningUnit.objects.filter(content_type='step_by_step', is_deleted=False),
        id=unit_id
    )

    # Проверка прав
    course = _get_unit_course(unit)
    if course:
        perm = _get_user_permission(user, course)
        allowed = {'edit', 'create_delete', 'full_access'}
        if perm not in allowed and not user.is_staff:
            messages.error(request, 'Нет доступа для экспорта.')
            return redirect('course:step_by_step_list')

    steps = unit.steps.order_by('order')
    steps_data = []
    for step in steps:
        questions = step.questions.order_by('order')
        questions_data = []
        for q in questions:
            choices = q.choices.all()
            choices_data = []
            for c in choices:
                choices_data.append({
                    'text': c.text,
                    'is_correct': c.is_correct,
                })
            questions_data.append({
                'text': q.text,
                'order': q.order,
                'choices': choices_data,
            })
        steps_data.append({
            'title': step.title,
            'content': step.content or '',
            'order': step.order,
            'questions': questions_data,
        })

    export_data = {
        'format_version': 1,
        'type': 'step_by_step_unit',
        'title': re.sub(r'\s*\(\d+\s+шагов\)\s*$', '', unit.title),
        'unit_id': unit.id,
        'exported_at': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
        'steps': steps_data,
    }

    json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
    clean_title = re.sub(r'\s*\(\d+\s+шагов\)\s*$', '', unit.title)
    safe_name = clean_title.replace(' ', '_')
    filename = f"step_unit_{safe_name}.json"
    response = HttpResponse(json_str, content_type='application/json')
    response['Content-Disposition'] = f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"
    return response




def _parse_step_by_step_json(file_obj):
    """Парсит JSON-файл, возвращает (data, error_msg)."""
    try:
        raw = file_obj.read().decode('utf-8-sig')
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return None, f'Ошибка чтения файла: {e}'

    if data.get('type') != 'step_by_step_unit':
        return None, 'Неверный формат файла — ожидается экспорт пошаговой единицы.'

    if not data.get('title') or not data.get('steps'):
        return None, 'Файл не содержит название единицы или шаги.'

    return data, None


@login_required
def step_by_step_import_page(request):
    """Страница импорта пошаговой единицы (проверка + предпросмотр + импорт)."""
    user = request.user
    if hasattr(user, 'fio'):
        messages.error(request, 'Только преподаватели могут импортировать пошаговые единицы.')
        return redirect('course:step_by_step_list')

    context = {}

    if request.method == 'POST':
        # Шаг 2: подтверждение импорта (title передан)
        title = request.POST.get('title', '').strip()

        if title:
            # Загружаем данные из сессии
            import_data = request.session.get('step_import_data')

            if not import_data:
                messages.error(request, 'Данные импорта утеряны. Загрузите файл заново.')
                return redirect('course:step_by_step_import_page')

            # Проверяем уникальность названия
            if LearningUnit.objects.filter(title__iexact=title, content_type='step_by_step', is_deleted=False).exists():
                context['error_message'] = f'Пошаговая единица с названием «{title}» уже существует. Измените название.'
                context['import_data'] = import_data
                context['steps_count'] = len(import_data.get('steps', []))
                return render(request, 'course/step_by_step_import.html', context)

            # Выполняем импорт из сессии
            steps_data = import_data.get('steps', [])
            unit = LearningUnit.objects.create(
                title=title,
                content_type='step_by_step',
            )
            for step_entry in steps_data:
                step = unit.steps.create(
                    title=step_entry.get('title', 'Без названия'),
                    content=step_entry.get('content', ''),
                    order=step_entry.get('order', 0),
                )
                for q_entry in step_entry.get('questions', []):
                    question = step.questions.create(
                        text=q_entry.get('text', ''),
                        order=q_entry.get('order', 0),
                    )
                    for c_entry in q_entry.get('choices', []):
                        question.choices.create(
                            text=c_entry.get('text', ''),
                            is_correct=c_entry.get('is_correct', False),
                        )

            del request.session['step_import_data']
            messages.success(
                request,
                f'Пошаговая единица «{title}» импортирована ({len(steps_data)} шагов). '
                f'Вы можете привязать её к курсу через редактор.'
            )
            return redirect('course:step_by_step_list')

        # Шаг 1: загрузка файла
        json_file = request.FILES.get('json_file')
        if not json_file:
            messages.error(request, 'Выберите файл для импорта.')
            return redirect('course:step_by_step_import_page')

        import_data, error = _parse_step_by_step_json(json_file)
        if error:
            messages.error(request, error)
            return redirect('course:step_by_step_import_page')

        # Сохраняем в сессию для следующего шага
        request.session['step_import_data'] = import_data
        context['import_data'] = import_data
        context['steps_count'] = len(import_data.get('steps', []))
    return render(request, 'course/step_by_step_import.html', context)


@login_required
def step_by_step_import(request):
    """Запасной путь — редирект на страницу импорта."""
    return redirect('course:step_by_step_import_page')


@login_required
@require_POST
def step_progress_reset_group(request, course_id, group_id):
    """Сброс прогресса группы по всем пошаговым единицам курса."""
    course = get_object_or_404(Course, id=course_id)
    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms:
        messages.error(request, 'У вас нет прав на сброс результатов.')
        return redirect('dashboard')

    from .models import StepProgress, Step
    step_units_qs = LearningUnit.objects.filter(
        django_models.Q(topic__section__course=course) | django_models.Q(section__course=course),
        content_type='step_by_step',
    )
    step_ids = Step.objects.filter(learning_unit__in=step_units_qs).values_list('id', flat=True)

    deleted_count, _ = StepProgress.objects.filter(
        student__group_id=group_id,
        step_id__in=step_ids,
    ).delete()

    from students.models import StudentGroup
    group = get_object_or_404(StudentGroup, id=group_id)
    messages.success(request, f'Результаты группы «{group.group_number}» сброшены. Студенты могут пройти пошаговые единицы заново.')
    return redirect('course:course_grades', course_id=course.id)


# ========== Пошаговые единицы ==========

@login_required
def step_by_step_list(request):
    """Список всех пошаговых единиц, сгруппированных по курсам."""
    user = request.user
    if hasattr(user, 'fio'):
        messages.error(request, 'Страница доступна только преподавателям.')
        return redirect('dashboard')

    # Собираем курсы, к которым у пользователя есть доступ
    if user.is_staff:
        courses = Course.objects.filter(is_deleted=False).prefetch_related(
            'sections__topics__units',
            'sections__direct_units',
        )
        all_courses_for_modal = courses
    else:
        allowed_course_ids = set()
        perms = CourseUserPermission.objects.filter(user=user).values_list('course_id', flat=True)
        allowed_course_ids.update(perms)
        for gp in CourseGroupPermission.objects.filter(group__in=user.groups.all()):
            allowed_course_ids.add(gp.course_id)
        courses = Course.objects.filter(id__in=allowed_course_ids, is_deleted=False).prefetch_related(
            'sections__topics__units',
            'sections__direct_units',
        )
        all_courses_for_modal = courses

    # Собираем все пошаговые единицы
    step_units_by_course = []
    for course in courses:
        step_units = []
        # Из тем
        for section in course.sections.all():
            for topic in section.topics.all():
                for unit in topic.units.filter(content_type='step_by_step'):
                    step_units.append({
                        'unit': unit,
                        'section_name': section.name,
                        'topic_content': topic.content,
                    })
            # Прямые единицы раздела
            for unit in section.direct_units.filter(content_type='step_by_step'):
                step_units.append({
                    'unit': unit,
                    'section_name': section.name,
                    'topic_content': None,
                })
        if step_units:
            step_units_by_course.append({
                'course': course,
                'step_units': step_units,
            })

    # Собираем непривязанные пошаговые единицы (без курса/раздела)
    unattached_units = list(
        LearningUnit.objects.filter(
            content_type='step_by_step',
            is_deleted=False,
            section__isnull=True,
            topic__isnull=True,
        ).order_by('-id')
    )

    if request.GET.get('api') == '1':
        from django.http import JsonResponse
        from .models import Step as StepModel
        # API: вернуть все step_by_step единицы
        api_units = list(
            LearningUnit.objects.filter(
                content_type='step_by_step',
                is_deleted=False,
            ).values('id', 'title').order_by('-id')
        )
        for u in api_units:
            u['steps_count'] = StepModel.objects.filter(learning_unit_id=u['id']).count()
        return JsonResponse({'units': list(api_units)})

    return render(request, 'course/step_by_step_list.html', {
        'step_units_by_course': step_units_by_course,
        'all_courses_for_modal': all_courses_for_modal,
        'unattached_units': unattached_units,
    })


@login_required
@require_POST
def step_by_step_soft_delete(request, unit_id):
    """Софт-удаление пошаговой единицы."""
    unit = get_object_or_404(LearningUnit, id=unit_id, content_type='step_by_step')
    from django.utils import timezone
    unit.is_deleted = True
    unit.deleted_at = timezone.now()
    unit.save()
    messages.success(request, f'Пошаговая единица «{unit.title}» перемещена в архив.')
    return redirect('course:step_by_step_list')


@login_required
def step_by_step_archive(request):
    """Архив удалённых пошаговых единиц."""
    user = request.user
    if hasattr(user, 'fio'):
        messages.error(request, 'Страница доступна только преподавателям.')
        return redirect('dashboard')

    deleted_units = LearningUnit.objects.filter(
        content_type='step_by_step',
        is_deleted=True,
    ).order_by('-deleted_at')

    return render(request, 'course/step_by_step_archive.html', {
        'deleted_units': deleted_units,
    })


@login_required
@require_POST
def step_by_step_restore(request, unit_id):
    """Восстановление удалённой пошаговой единицы."""
    unit = get_object_or_404(LearningUnit, id=unit_id, content_type='step_by_step', is_deleted=True)
    unit.is_deleted = False
    unit.deleted_at = None
    unit.save()
    messages.success(request, f'Пошаговая единица «{unit.title}» восстановлена.')
    return redirect('course:step_by_step_list')


@login_required
@require_POST
def step_by_step_hard_delete(request, unit_id):
    """Полное удаление пошаговой единицы (только администраторы)."""
    if not request.user.is_staff:
        messages.error(request, 'Только администраторы могут полностью удалять единицы.')
        return redirect('course:step_by_step_archive')

    unit = get_object_or_404(LearningUnit, id=unit_id, content_type='step_by_step', is_deleted=True)

    # Удаляем файл если есть
    if unit.file and os.path.isfile(unit.file.path):
        os.remove(unit.file.path)

    title = unit.title
    unit.delete()
    messages.success(request, f'Пошаговая единица «{title}» полностью удалена.')
    return redirect('course:step_by_step_archive')

@login_required
def step_by_step_create(request):
    """Создание новой пошаговой единицы — без привязки к курсу (будет позже)."""
    user = request.user
    if hasattr(user, 'fio'):
        messages.error(request, 'Только преподаватели.')
        return redirect('dashboard')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()

        if not title:
            messages.error(request, 'Название единицы обязательно.')
            return redirect('course:step_by_step_list')

        unit = LearningUnit.objects.create(
            title=title,
            content_type='step_by_step',
            order=1,
        )
        messages.success(request, f'Пошаговая единица «{title}» создана. Назначьте курс и раздел позже в редакторе.')
        return redirect('course:step_by_step_wizard', unit_id=unit.id)

    return redirect('course:step_by_step_list')


@login_required
def step_by_step_wizard(request, unit_id):
    """Пошаговый визард создания/редактирования шагов и вопросов."""
    unit = get_object_or_404(LearningUnit.objects.prefetch_related('steps__questions__choices'), id=unit_id, content_type='step_by_step')

    if unit.topic:
        course = unit.topic.section.course
    elif unit.section:
        course = unit.section.course
    else:
        course = None

    if course:
        user_perm = _get_user_permission(request.user, course)
        allowed_perms = {'edit', 'create_delete', 'full_access'}
        if user_perm not in allowed_perms:
            messages.error(request, 'У вас нет прав.')
            return redirect('dashboard')

    steps = unit.steps.all()

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'add_step':
            # Добавляем новый шаг
            from .models import Step
            step_title = request.POST.get('step_title', '').strip()
            step_content = request.POST.get('step_content', '').strip()

            if not step_title:
                messages.error(request, 'Название шага обязательно.')
                return redirect('course:step_by_step_wizard', unit_id=unit.id)

            last_step = unit.steps.order_by('-order').first()
            next_order = (last_step.order + 1) if last_step else 1

            step = Step.objects.create(
                learning_unit=unit,
                title=step_title,
                content=step_content if step_content else None,
                order=next_order,
            )

            # Добавляем вопросы к этому шагу
            from .models import StepQuestion, StepChoice
            question_texts = request.POST.getlist('question_text[]', [])
            for qi, qt in enumerate(question_texts):
                qt = qt.strip()
                if qt:
                    last_q = step.questions.order_by('-order').first()
                    q_order = (last_q.order + 1) if last_q else 1
                    q = StepQuestion.objects.create(step=step, text=qt, order=q_order)

                    # Варианты ответов для этого вопроса (по индексу вопроса)
                    choice_texts = request.POST.getlist(f'choice_text_{qi}[]', [])
                    correct_indices = set(int(i) for i in request.POST.getlist(f'choice_correct_{qi}[]', []) if i.isdigit())
                    for idx, ct in enumerate(choice_texts):
                        ct = ct.strip()
                        if ct:
                            StepChoice.objects.create(
                                question=q, text=ct,
                                is_correct=(idx in correct_indices),
                            )

            messages.success(request, f'Шаг «{step_title}» добавлен с вопросами.')

        elif action == 'finish':
            messages.success(request, f'Создание пошаговой единицы «{unit.title}» завершено.')
            return redirect('course:step_by_step_list')

        return redirect('course:step_by_step_wizard', unit_id=unit.id)

    return render(request, 'course/step_by_step_wizard.html', {
        'unit': unit,
        'course': course,
        'steps': steps,
    })


@login_required
def step_by_step_preview(request, unit_id):
    """Предпросмотр пошаговой единицы (без проверки ответов)."""
    unit = get_object_or_404(
        LearningUnit.objects.prefetch_related('steps__questions__choices'),
        id=unit_id, content_type='step_by_step', is_deleted=False
    )

    steps = list(unit.steps.order_by('order'))
    if not steps:
        messages.error(request, 'В пошаговой единице нет шагов.')
        return redirect('course:step_by_step_list')

    # Текущий шаг по GET-параметру, по умолчанию первый
    try:
        current_index = int(request.GET.get('step', 0))
    except (ValueError, TypeError):
        current_index = 0

    if current_index < 0:
        current_index = 0
    if current_index >= len(steps):
        current_index = len(steps) - 1

    current_step = steps[current_index]
    prev_index = current_index - 1 if current_index > 0 else None
    next_index = current_index + 1 if current_index < len(steps) - 1 else None

    return render(request, 'course/step_by_step_preview.html', {
        'unit': unit,
        'current_step': current_step,
        'steps': steps,
        'current_index': current_index,
        'prev_index': prev_index,
        'next_index': next_index,
    })


def step_by_step_edit(request, unit_id):
    """Редактирование шагов пошаговой единицы."""
    unit = get_object_or_404(LearningUnit.objects.prefetch_related('steps__questions__choices'), id=unit_id, content_type='step_by_step')

    course = _get_unit_course(unit)

    if course is not None:
        user_perm = _get_user_permission(request.user, course)
        allowed_perms = {'edit', 'create_delete', 'full_access'}
        if user_perm not in allowed_perms:
            messages.error(request, 'У вас нет прав на редактирование пошаговой единицы.')
            return redirect('dashboard')

    steps = unit.steps.all()

    context = {
        'unit': unit,
        'course': course,
        'steps': steps,
    }
    return render(request, 'course/step_by_step_edit.html', context)


@login_required
@require_POST
def step_add(request, unit_id):
    """Добавление шага к пошаговой единице."""
    unit = get_object_or_404(LearningUnit, id=unit_id, content_type='step_by_step')

    course = _get_unit_course(unit)

    if course is not None:
        user_perm = _get_user_permission(request.user, course)
        allowed_perms = {'edit', 'create_delete', 'full_access'}
        if user_perm not in allowed_perms:
            messages.error(request, 'У вас нет прав.')
            return redirect('dashboard')

    title = request.POST.get('title', '').strip()
    content = request.POST.get('content', '').strip()

    if not title:
        messages.error(request, 'Название шага обязательно.')
        return redirect('course:step_by_step_edit', unit_id=unit.id)

    from .models import Step
    last_step = unit.steps.order_by('-order').first()
    next_order = (last_step.order + 1) if last_step else 1

    Step.objects.create(
        learning_unit=unit,
        title=title,
        content=content if content else None,
        order=next_order,
    )
    messages.success(request, f'Шаг «{title}» добавлен.')
    return redirect('course:step_by_step_edit', unit_id=unit.id)


@login_required
@require_POST
def step_edit(request, step_id):
    """Редактирование шага."""
    from .models import Step
    step = get_object_or_404(Step.objects.select_related('learning_unit'), id=step_id)
    unit = step.learning_unit

    course = _get_unit_course(unit)

    if course is not None:
        user_perm = _get_user_permission(request.user, course)
        allowed_perms = {'edit', 'create_delete', 'full_access'}
        if user_perm not in allowed_perms:
            messages.error(request, 'У вас нет прав.')
            return redirect('dashboard')

    title = request.POST.get('title', '').strip()
    content = request.POST.get('content', '').strip()

    if not title:
        messages.error(request, 'Название шага обязательно.')
        return redirect('course:step_by_step_edit', unit_id=unit.id)

    step.title = title
    step.content = content if content else None
    step.save()
    messages.success(request, f'Шаг «{title}» обновлён.')
    return redirect('course:step_by_step_edit', unit_id=unit.id)


@login_required
@require_POST
def step_delete(request, step_id):
    """Удаление шага."""
    from .models import Step
    step = get_object_or_404(Step.objects.select_related('learning_unit'), id=step_id)
    unit = step.learning_unit

    course = _get_unit_course(unit)

    if course is not None:
        user_perm = _get_user_permission(request.user, course)
        allowed_perms = {'edit', 'create_delete', 'full_access'}
        if user_perm not in allowed_perms:
            messages.error(request, 'У вас нет прав.')
            return redirect('dashboard')

    title = step.title
    step.delete()
    messages.success(request, f'Шаг «{title}» удалён.')
    return redirect('course:step_by_step_edit', unit_id=unit.id)


@login_required
@require_POST
def step_question_add(request, step_id):
    """Добавление вопроса к шагу."""
    from .models import Step, StepQuestion
    step = get_object_or_404(Step.objects.select_related('learning_unit'), id=step_id)
    unit = step.learning_unit

    course = _get_unit_course(unit)

    if course is not None:
        user_perm = _get_user_permission(request.user, course)
        allowed_perms = {'edit', 'create_delete', 'full_access'}
        if user_perm not in allowed_perms:
            messages.error(request, 'У вас нет прав.')
            return redirect('dashboard')

    text = request.POST.get('text', '').strip()
    if not text:
        messages.error(request, 'Текст вопроса обязателен.')
        return redirect('course:step_by_step_edit', unit_id=unit.id)

    last_q = step.questions.order_by('-order').first()
    next_order = (last_q.order + 1) if last_q else 1

    question = StepQuestion.objects.create(
        step=step,
        text=text,
        order=next_order,
    )

    # Добавляем варианты ответов
    from .models import StepChoice
    choice_texts = request.POST.getlist('choice_text[]', [])
    correct_indices = set(int(i) for i in request.POST.getlist('choice_correct[]', []) if i.isdigit())

    for idx, ct in enumerate(choice_texts):
        ct = ct.strip()
        if ct:
            StepChoice.objects.create(
                question=question,
                text=ct,
                is_correct=(idx in correct_indices),
            )

    messages.success(request, 'Вопрос добавлен.')
    return redirect('course:step_by_step_edit', unit_id=unit.id)


@login_required
@require_POST
def step_question_edit(request, question_id):
    """Редактирование вопроса и его вариантов ответа."""
    from .models import StepQuestion, StepChoice
    question = get_object_or_404(
        StepQuestion.objects.select_related('step__learning_unit'), id=question_id
    )
    step = question.step
    unit = step.learning_unit

    course = _get_unit_course(unit)

    if course is not None:
        user_perm = _get_user_permission(request.user, course)
        allowed_perms = {'edit', 'create_delete', 'full_access'}
        if user_perm not in allowed_perms:
            messages.error(request, 'У вас нет прав.')
            return redirect('dashboard')

    text = request.POST.get('text', '').strip()
    if not text:
        messages.error(request, 'Текст вопроса обязателен.')
        return redirect('course:step_by_step_edit', unit_id=unit.id)

    question.text = text
    question.save()

    # Удаляем старые варианты и создаём новые
    question.choices.all().delete()

    choice_texts = request.POST.getlist('choice_text[]', [])
    correct_indices = set(int(i) for i in request.POST.getlist('choice_correct[]', []) if i.isdigit())

    for idx, ct in enumerate(choice_texts):
        ct = ct.strip()
        if ct:
            StepChoice.objects.create(
                question=question,
                text=ct,
                is_correct=(idx in correct_indices),
            )

    messages.success(request, 'Вопрос обновлён.')
    return redirect('course:step_by_step_edit', unit_id=unit.id)


@login_required
@require_POST
def step_question_delete(request, question_id):
    """Удаление вопроса."""
    from .models import StepQuestion
    question = get_object_or_404(
        StepQuestion.objects.select_related('step__learning_unit'), id=question_id
    )
    unit = question.step.learning_unit

    course = _get_unit_course(unit)

    if course is not None:
        user_perm = _get_user_permission(request.user, course)
        allowed_perms = {'edit', 'create_delete', 'full_access'}
        if user_perm not in allowed_perms:
            messages.error(request, 'У вас нет прав.')
            return redirect('dashboard')

    question.delete()
    messages.success(request, 'Вопрос удалён.')
    return redirect('course:step_by_step_edit', unit_id=unit.id)


@login_required
def step_by_step_take(request, unit_id):
    """Прохождение пошаговой единицы студентом."""
    user = request.user
    if not hasattr(user, 'fio'):
        messages.error(request, 'Только студенты могут проходить пошаговые единицы.')
        return redirect('dashboard')

    unit = get_object_or_404(
        LearningUnit.objects.prefetch_related('steps__questions__choices'),
        id=unit_id, content_type='step_by_step'
    )

    course = _get_unit_course(unit)

    if course is not None:
        if not CourseGroupStudent.objects.filter(course=course, group_id=user.group_id).exists():
            messages.error(request, 'Вы не подписаны на этот курс.')
            return redirect('index')

    steps = list(unit.steps.order_by('order'))
    if not steps:
        messages.error(request, 'В пошаговой единице нет шагов.')
        if course:
            return redirect('course:course_view', course_id=course.id)
        return redirect('index')

    # Определяем текущий шаг (первый непройденный)
    from .models import StepProgress
    completed_step_ids = set(
        StepProgress.objects.filter(student=user, step__learning_unit=unit, completed=True)
        .values_list('step_id', flat=True)
    )

    current_step = None
    for step in steps:
        if step.id not in completed_step_ids:
            current_step = step
            break

    if not current_step:
        # Все шаги пройдены — режим просмотра материалов и своих ответов
        progress_list = list(
            StepProgress.objects.filter(student=user, step__learning_unit=unit)
        )
        progress_map = {p.step_id: p for p in progress_list}

        # Текущий шаг для просмотра по GET-параметру, по умолчанию первый
        try:
            view_index = int(request.GET.get('step', 0))
        except (ValueError, TypeError):
            view_index = 0
        if view_index < 0:
            view_index = 0
        if view_index >= len(steps):
            view_index = len(steps) - 1

        view_step = steps[view_index]
        view_questions = list(view_step.questions.prefetch_related('choices').all())
        view_progress = progress_map.get(view_step.id)

        # Собираем ID выбранных студентом вариантов
        chosen_choice_ids = set()
        if view_progress and view_progress.answers:
            for q_id, choice_ids in view_progress.answers.items():
                chosen_choice_ids.update(choice_ids)

        return render(request, 'course/step_by_step_take.html', {
            'unit': unit,
            'course': course,
            'all_completed': True,
            'read_only': True,
            'current_step': view_step,
            'current_index': view_index,
            'steps': steps,
            'completed_step_ids': completed_step_ids,
            'questions': view_questions,
            'progress': view_progress,
            'chosen_choice_ids': chosen_choice_ids,
            'prev_index': view_index - 1 if view_index > 0 else None,
            'next_index': view_index + 1 if view_index < len(steps) - 1 else None,
        })

    if request.method == 'POST':
        # Сохраняем ответы студента (без проверки правильности — для анализа усвояемости)
        from django.utils import timezone
        questions = list(current_step.questions.prefetch_related('choices').all())
        answers = {}
        for q in questions:
            choice_ids = request.POST.getlist(f'q_{q.id}')
            chosen_ids = [int(c) for c in choice_ids if c.isdigit()]
            if chosen_ids:
                answers[str(q.id)] = chosen_ids

        # Отмечаем шаг как пройденный и сохраняем ответы
        StepProgress.objects.update_or_create(
            student=user,
            step=current_step,
            defaults={
                'completed': True,
                'completed_at': timezone.now(),
                'answers': answers if answers else None,
            },
        )
        messages.success(request, f'Шаг «{current_step.title}» пройден!')
        return redirect('course:step_by_step_take', unit_id=unit.id)

    # Отображаем текущий шаг с вопросами
    questions = list(current_step.questions.prefetch_related('choices').all())
    return render(request, 'course/step_by_step_take.html', {
        'unit': unit,
        'course': course,
        'current_step': current_step,
        'steps': steps,
        'completed_step_ids': completed_step_ids,
        'questions': questions,
        'is_last_step': (current_step.id == steps[-1].id),
    })


# --- Права преподавателей ---

@login_required
@require_POST
def teacher_permission_add(request, course_id):
    """Добавить право преподавателю на курс."""
    course = get_object_or_404(Course, id=course_id)
    user_perm = _get_user_permission(request.user, course)
    if user_perm not in {'full_access'} and not request.user.is_staff:
        messages.error(request, 'Только владелец курса может управлять правами.')
        return redirect('dashboard')

    user_id = request.POST.get('user_id', '')
    permission = request.POST.get('permission', 'view')
    if not user_id:
        messages.error(request, 'Выберите преподавателя.')
        return redirect('course:course_edit', course_id=course.id)
    if permission not in dict(CourseUserPermission.PERMISSION_CHOICES):
        messages.error(request, 'Недопустимый уровень прав.')
        return redirect('course:course_edit', course_id=course.id)

    try:
        user = User.objects.get(id=int(user_id), is_active=True, is_staff=True)
    except (User.DoesNotExist, ValueError, TypeError):
        messages.error(request, 'Преподаватель не найден.')
        return redirect('course:course_edit', course_id=course.id)

    CourseUserPermission.objects.update_or_create(
        course=course,
        user=user,
        defaults={'permission': permission},
    )
    name = user.get_full_name() or user.get_username()
    messages.success(request, f'Права «{name}» обновлены ({permission}).')
    return redirect('course:course_edit', course_id=course.id)


@login_required
@require_POST
def teacher_permission_remove(request, course_id, up_id):
    """Удалить право преподавателя на курс."""
    course = get_object_or_404(Course, id=course_id)
    user_perm = _get_user_permission(request.user, course)
    if user_perm not in {'full_access'} and not request.user.is_staff:
        messages.error(request, 'Только владелец курса может управлять правами.')
        return redirect('dashboard')

    up = get_object_or_404(CourseUserPermission, id=up_id, course=course)
    name = up.user.get_full_name() or up.user.get_username()
    up.delete()
    messages.success(request, f'Права «{name}» удалены.')
    return redirect('course:course_edit', course_id=course.id)


@login_required
@require_POST
def group_permission_add(request, course_id):
    """Добавить право группе преподавателей на курс."""
    course = get_object_or_404(Course, id=course_id)
    user_perm = _get_user_permission(request.user, course)
    if user_perm not in {'full_access'} and not request.user.is_staff:
        messages.error(request, 'Только владелец курса может управлять правами.')
        return redirect('dashboard')

    group_id = request.POST.get('group_id', '')
    permission = request.POST.get('permission', 'view')
    if not group_id:
        messages.error(request, 'Выберите группу.')
        return redirect('course:course_edit', course_id=course.id)
    if permission not in dict(CourseGroupPermission.PERMISSION_CHOICES):
        messages.error(request, 'Недопустимый уровень прав.')
        return redirect('course:course_edit', course_id=course.id)

    try:
        group = Group.objects.get(id=int(group_id))
    except (Group.DoesNotExist, ValueError, TypeError):
        messages.error(request, 'Группа не найдена.')
        return redirect('course:course_edit', course_id=course.id)

    CourseGroupPermission.objects.update_or_create(
        course=course,
        group=group,
        defaults={'permission': permission},
    )
    messages.success(request, f'Права группы «{group.name}» обновлены ({permission}).')
    return redirect('course:course_edit', course_id=course.id)


@login_required
@require_POST
def group_permission_remove(request, course_id, gp_id):
    """Удалить право группы преподавателей на курс."""
    course = get_object_or_404(Course, id=course_id)
    user_perm = _get_user_permission(request.user, course)
    if user_perm not in {'full_access'} and not request.user.is_staff:
        messages.error(request, 'Только владелец курса может управлять правами.')
        return redirect('dashboard')

    gp = get_object_or_404(CourseGroupPermission, id=gp_id, course=course)
    name = gp.group.name
    gp.delete()
    messages.success(request, f'Права группы «{name}» удалены.')
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
    """При создании курса:
    - создателю — полный доступ
    - декану соответствующего факультета — просмотр
    - зав. кафедрой соответствующей кафедры — просмотр
    - группы «УМО» и «Ректорат» — просмотр (всем участникам группы)
    """
    # Создатель — полный доступ
    CourseUserPermission.objects.get_or_create(
        course=course,
        user=creator,
        defaults={'permission': 'full_access'},
    )
    try:
        department = course.subject.department
    except Exception:
        department = None

    # Декан факультета — персональное право просмотра
    if department:
        faculty = department.faculty
        if faculty and faculty.dean:
            CourseUserPermission.objects.get_or_create(
                course=course,
                user=faculty.dean,
                defaults={'permission': 'view'},
            )
        # Заведующий кафедрой — персональное право просмотра
        if department.head:
            CourseUserPermission.objects.get_or_create(
                course=course,
                user=department.head,
                defaults={'permission': 'view'},
            )

    # Группы УМО и Ректорат — просмотр (всем участникам групп)
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
    """Добавляет разделы по умолчанию к новому курсу.
    «Пояснительный» и «Преподавательский» — скрыты от студентов."""
    HIDDEN = {'Пояснительный', 'Преподавательский'}
    for i, name in enumerate(CourseSection.DEFAULT_SECTIONS, start=1):
        defaults = {'order': i}
        if name in HIDDEN:
            defaults['visible'] = False
        CourseSection.objects.get_or_create(
            course=course,
            name=name,
            defaults=defaults,
        )


@login_required
@require_POST
def course_delete(request, course_id):
    """Софт-удаление курса."""
    user_perm = None
    course = get_object_or_404(Course, id=course_id)
    if not course.is_deleted:
        user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'create_delete', 'full_access'}
    if user_perm not in allowed_perms and not request.user.is_staff:
        messages.error(request, 'У вас нет прав на удаление курса.')
        return redirect('dashboard')

    from django.utils import timezone
    course.is_deleted = True
    course.deleted_at = timezone.now()
    course.save()
    messages.success(request, f'Курс «{course.short_name}» перемещён в архив.')
    return redirect('dashboard')

@login_required
@require_POST
def course_hard_delete(request, course_id):
    """Полное удаление курса (только администраторы)."""
    if not request.user.is_staff:
        messages.error(request, 'Только администраторы могут полностью удалять курсы.')
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
    messages.success(request, f'Курс «{course_name}» полностью удалён.')
    return redirect('dashboard')



@login_required
@require_POST
def course_clone(request, course_id):
    """Клонирование курса со всем содержимым и правами."""
    course = get_object_or_404(Course, id=course_id)

    # Проверяем права: клонировать могут те же, кто редактирует
    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'edit', 'create_delete', 'full_access'}
    if user_perm not in allowed_perms and not request.user.is_staff:
        messages.error(request, 'У вас нет прав на клонирование курса.')
        return redirect('dashboard')

    # Генерируем уникальное имя/identifier
    new_full_name = f'КЛОН {course.full_name}'
    new_short_name = f'КЛОН {course.short_name}'
    new_identifier = (f'clone_{course.identifier}' if course.identifier else f'clone_{course.id}')

    # Проверяем уникальность и если занято — добавляем суффикс
    base_identifier = new_identifier
    counter = 1
    while Course.objects.filter(identifier=new_identifier).exists():
        new_identifier = f'{base_identifier}_{counter}'
        new_short_name = f'КЛОН {course.short_name} ({counter})'
        new_full_name = f'КЛОН {course.full_name} ({counter})'
        counter += 1

    # Создаём новый курс
    new_course = Course.objects.create(
        subject=course.subject,
        full_name=new_full_name,
        short_name=new_short_name,
        identifier=new_identifier,
    )

    # Клонируем разделы с темами и единицами
    for section in course.sections.all():
        new_section = CourseSection.objects.create(
            course=new_course,
            name=section.name,
            order=section.order,
            visible=section.visible,
        )
        for topic in section.topics.all():
            new_topic = CourseTopic.objects.create(
                section=new_section,
                entity_title=topic.entity_title,
                content=topic.content,
                order=topic.order,
                visible=topic.visible,
            )
            for unit in topic.units.all():
                LearningUnit.objects.create(
                    topic=new_topic,
                    section=None,
                    title=unit.title,
                    content_type=unit.content_type,
                    file=unit.file,
                    link=unit.link,
                    order=unit.order,
                    visible=unit.visible,
                    grading_type=unit.grading_type,
                    max_score=unit.max_score,
                    test=unit.test,
                )
        for unit in section.direct_units.all():
            LearningUnit.objects.create(
                section=new_section,
                topic=None,
                title=unit.title,
                content_type=unit.content_type,
                file=unit.file,
                link=unit.link,
                order=unit.order,
                visible=unit.visible,
                grading_type=unit.grading_type,
                max_score=unit.max_score,
                test=unit.test,
            )

    # Клонируем права
    for up in course.user_permissions.all():
        CourseUserPermission.objects.create(
            course=new_course,
            user=up.user,
            permission=up.permission,
        )
    for gp in course.group_permissions.all():
        CourseGroupPermission.objects.create(
            course=new_course,
            group=gp.group,
            permission=gp.permission,
        )

    # Группы студентов НЕ клонируем — у клона будут другие группы

    messages.info(request, f'Клонирование завершено: разделов — {course.sections.count()}, тем — {sum(s.topics.count() for s in course.sections.all())}, единиц — {sum(s.topics.aggregate(c=models.Count("units"))["c"] or 0 for s in course.sections.all())}')
    messages.success(request, f'Курс «{new_short_name}» создан как клон «{course.short_name}».')
    return redirect('course:course_edit', course_id=new_course.id)


@login_required
def course_archive(request):
    """Архив удалённых курсов."""
    user = request.user
    if hasattr(user, 'fio'):
        messages.error(request, 'Страница доступна только преподавателям.')
        return redirect('dashboard')

    if user.is_staff:
        deleted_courses = Course.objects.filter(is_deleted=True).select_related('subject__department').order_by('-deleted_at')
    else:
        allowed_ids = set()
        perms = CourseUserPermission.objects.filter(user=user).values_list('course_id', flat=True)
        allowed_ids.update(perms)
        for gp in CourseGroupPermission.objects.filter(group__in=user.groups.all()):
            allowed_ids.add(gp.course_id)
        deleted_courses = Course.objects.filter(id__in=allowed_ids, is_deleted=True).select_related('subject__department').order_by('-deleted_at')

    return render(request, 'course/archive.html', {
        'deleted_courses': deleted_courses,
    })


@login_required
@require_POST
def course_restore(request, course_id):
    """Восстановление курса из архива."""
    course = get_object_or_404(Course, id=course_id, is_deleted=True)

    user_perm = _get_user_permission(request.user, course)
    allowed_perms = {'create_delete', 'full_access'}
    if user_perm not in allowed_perms and not request.user.is_staff:
        messages.error(request, 'У вас нет прав на восстановление курса.')
        return redirect('course:course_archive')

    course.is_deleted = False
    course.deleted_at = None
    course.save()
    messages.success(request, f'Курс «{course.short_name}» восстановлен.')
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
    course = _get_unit_course(answer.learning_unit)

    # Проверяем права
    if course is not None:
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

    # --- Пошаговые единицы ---
    from .models import StepProgress, Step, StepQuestion, StepChoice
    step_units_qs = LearningUnit.objects.filter(
        django_models.Q(topic__section__course=course) | django_models.Q(section__course=course),
        content_type='step_by_step',
    ).prefetch_related('steps__questions__choices').order_by('order', 'id')
    all_step_units = list(step_units_qs)

    # Собираем все вопросы и правильные ответы для всех пошаговых единиц
    step_questions_info = {}  # {question_id: [correct_choice_id, ...]}
    unit_questions_map = {}   # {unit_id: [question_id, ...]}
    question_step_map = {}    # {question_id: step_id}
    step_order_map = {}       # {step_id: order}
    for su in all_step_units:
        unit_questions_map[su.id] = []
        for step in su.steps.all():
            for q in step.questions.all():
                unit_questions_map[su.id].append(q.id)
                question_step_map[q.id] = step.id
                step_order_map[step.id] = step.order
                correct_ids = list(q.choices.filter(is_correct=True).values_list('id', flat=True))
                step_questions_info[q.id] = correct_ids

    # Собираем прогресс для всех студентов
    all_step_question_ids = list(step_questions_info.keys())
    step_progress_qs = StepProgress.objects.filter(
        student_id__in=[s.id for eg in enrolled for s in eg.group.students.all()],
        step__learning_unit__in=all_step_units,
    ).select_related('step')

    # Строим матрицу прогресса: {student_id: {step_id: progress}}
    step_progress_matrix = {}
    for sp in step_progress_qs:
        step_progress_matrix.setdefault(sp.student_id, {})[sp.step_id] = sp

    # Матрица ответов: {student_id: {question_id: [chosen_ids]}}
    step_answers_matrix = {}
    for sp in step_progress_qs:
        if sp.answers:
            sid = sp.student_id
            step_answers_matrix.setdefault(sid, {})
            for q_id_str, chosen_ids in sp.answers.items():
                step_answers_matrix[sid][int(q_id_str)] = chosen_ids

    step_units_groups_data = []
    for eg in enrolled:
        group = eg.group
        students = group.students.all().order_by('fio')
        step_student_rows = []

        for student in students:
            spm = step_progress_matrix.get(student.id, {})
            sam = step_answers_matrix.get(student.id, {})
            unit_cells = []
            student_step_total = 0
            student_step_possible = 0

            for su in all_step_units:
                q_ids = unit_questions_map.get(su.id, [])
                unit_score = 0
                unit_possible = len(q_ids)
                # Считаем баллы за каждый вопрос: верный = 1, неверный = 0
                for qid in q_ids:
                    chosen = set(sam.get(qid, []))
                    correct = set(step_questions_info.get(qid, []))
                    if correct and chosen == correct:
                        unit_score += 1

                # Собираем детали по шагам
                step_details = []
                for step in su.steps.order_by('order'):
                    step_q_ids = [qid for qid in q_ids if question_step_map.get(qid) == step.id]
                    step_score = 0
                    step_possible = len(step_q_ids)
                    step_answered = False
                    for qid in step_q_ids:
                        chosen = set(sam.get(qid, []))
                        correct = set(step_questions_info.get(qid, []))
                        if correct and chosen == correct:
                            step_score += 1
                        if chosen:
                            step_answered = True
                    progress = spm.get(step.id)
                    step_details.append({
                        'step': step,
                        'score': step_score,
                        'possible': step_possible,
                        'completed': progress.completed if progress else False,
                        'answered': step_answered,
                    })

                student_step_total += unit_score
                student_step_possible += unit_possible
                unit_cells.append({
                    'unit': su,
                    'score': unit_score,
                    'possible': unit_possible,
                    'step_details': step_details,
                })

            step_student_rows.append({
                'student': student,
                'unit_cells': unit_cells,
                'total_score': student_step_total,
                'possible_score': student_step_possible,
            })

        step_units_groups_data.append({
            'group': group,
            'student_rows': step_student_rows,
            'step_units': all_step_units,
        })

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
        'step_units_groups_data': step_units_groups_data,
        'all_step_units': all_step_units,
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
    course = _get_unit_course(unit)

    # Проверяем подписку
    if course is not None:
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
        if course:
            return redirect('course:course_view', course_id=course.id)
        return redirect('index')

    if course:
        return redirect('course:course_view', course_id=course.id)
    return redirect('index')


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
        course = _get_course_for_unit(unit)
        if course:
            return redirect('course:course_view', course_id=course.id)
        return redirect('index')

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
    """Возвращает курс, к которому относится единица (использует _get_unit_course)."""
    return _get_unit_course(unit)


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
    # Прогресс пошаговых единиц: {unit_id: (answered_steps, total_steps)}
    step_progress_map = {}
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

        # Собираем прогресс по пошаговым единицам
        from .models import StepProgress, Step
        step_unit_ids = LearningUnit.objects.filter(
            django_models.Q(topic__section__course=course) | django_models.Q(section__course=course),
            content_type='step_by_step',
        ).values_list('id', flat=True)
        # Все шаги всех пошаговых единиц
        all_steps = Step.objects.filter(learning_unit_id__in=step_unit_ids).values('id', 'learning_unit_id')
        unit_total_steps = {}  # {unit_id: total}
        for s in all_steps:
            unit_total_steps[s['learning_unit_id']] = unit_total_steps.get(s['learning_unit_id'], 0) + 1
        # Шаги, на которые студент ответил (completed=True)
        answered_steps = set(
            StepProgress.objects.filter(
                student=user,
                step__learning_unit_id__in=step_unit_ids,
                completed=True,
            ).values_list('step_id', flat=True)
        )
        for s in all_steps:
            uid = s['learning_unit_id']
            total = unit_total_steps.get(uid, 0)
            answered = unit_total_steps.get(uid, 0)
            # Пересчитаем правильно
        # Упрощённый подход: считаем answered/total на unit
        for uid in step_unit_ids:
            total = unit_total_steps.get(uid, 0)
            if total == 0:
                step_progress_map[uid] = (0, 0)
                continue
            answered = StepProgress.objects.filter(
                student=user,
                step__learning_unit_id=uid,
                completed=True,
            ).count()
            step_progress_map[uid] = (answered, total)

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
        'step_progress_map': step_progress_map,
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

    course = _get_unit_course(unit)

    if course is not None:
        user_perm = _get_user_permission(request.user, course)
        allowed_perms = {'edit', 'create_delete', 'full_access'}
        if user_perm not in allowed_perms:
            messages.error(request, 'У вас нет прав на изменение видимости единицы.')
            return redirect('dashboard')

    unit.visible = not unit.visible
    unit.save(update_fields=['visible'])
    state = 'видима' if unit.visible else 'скрыта'
    messages.success(request, f'Единица «{unit.title}» теперь {state} для студентов.')
    if course:
        return redirect('course:course_edit', course_id=course.id)
    return redirect('course:step_by_step_list')


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
    course = _get_unit_course(unit)

    # Проверяем права
    if course is not None:
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
            if new_content_type not in ('control', 'step_by_step'):
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

    # Если пошаговая — проверяем, не выбрана ли существующая единица
    step_by_step_id = request.POST.get('step_by_step_id', '').strip()
    if content_type == 'step_by_step' and step_by_step_id:
        try:
            existing_unit = LearningUnit.objects.get(
                id=int(step_by_step_id),
                content_type='step_by_step',
                is_deleted=False,
            )
            # Привязываем существующую единицу к разделу/теме
            existing_unit.topic = topic
            existing_unit.section = section
            existing_unit.save()
            messages.success(request, f'Пошаговая единица «{existing_unit.title}» прикреплена.')
            return redirect('course:course_edit', course_id=course.id)
        except (LearningUnit.DoesNotExist, ValueError, TypeError):
            pass  # продолжаем обычное создание

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
    course = _get_unit_course(unit)

    # Проверяем права
    if course is not None:
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