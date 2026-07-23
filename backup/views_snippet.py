# Эти функции будут добавлены в конец msudle/course/views.py


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
    course = unit.topic.section.course if unit.topic else unit.section.course
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
        'title': unit.title,
        'unit_id': unit.id,
        'exported_at': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
        'steps': steps_data,
    }

    response = JsonResponse(export_data, json_dumps_params={'ensure_ascii': False, 'indent': 2})
    filename = f'step_unit_{unit.title.replace(" ", "_")}.json'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def step_by_step_import(request):
    """Импорт пошаговой единицы из JSON файла (только для преподавателей)."""
    user = request.user
    if hasattr(user, 'fio'):
        messages.error(request, 'Только преподаватели могут импортировать пошаговые единицы.')
        return redirect('course:step_by_step_list')

    if request.method == 'POST':
        json_file = request.FILES.get('json_file')
        if not json_file:
            messages.error(request, 'Выберите файл для импорта.')
            return redirect('course:step_by_step_list')

        try:
            data = json.loads(json_file.read().decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            messages.error(request, f'Ошибка чтения файла: {e}')
            return redirect('course:step_by_step_list')

        if data.get('type') != 'step_by_step_unit':
            messages.error(request, 'Неверный формат файла — ожидается экспорт пошаговой единицы.')
            return redirect('course:step_by_step_list')

        title = data.get('title', 'Без названия')
        steps_data = data.get('steps', [])

        if not title or not steps_data:
            messages.error(request, 'Файл не содержит название единицы или шаги.')
            return redirect('course:step_by_step_list')

        # Создаём новую пошаговую единицу (без привязки к курсу)
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

        messages.success(
            request,
            f'Пошаговая единица «{title}» импортирована ({len(steps_data)} шагов). '
            f'Вы можете привязать её к курсу через редактор.'
        )
        return redirect('course:step_by_step_list')

    return redirect('course:step_by_step_list')