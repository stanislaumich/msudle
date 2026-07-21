import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from .models import Test, Question, Choice, DeletedTest
from subject.models import Subject


def _is_teacher(user):
    """Проверка: пользователь — сотрудник (User), а не студент."""
    return not hasattr(user, 'fio')


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def test_list(request):
    """Список тестов преподавателя с пагинацией."""
    subjects = Subject.objects.all().order_by('full_name')
    tests = Test.objects.select_related('subject', 'author').order_by('-created_at')

    # Фильтр по дисциплине
    subject_id = request.GET.get('subject')
    if subject_id:
        tests = tests.filter(subject_id=subject_id)

    # Поиск по названию
    search = request.GET.get('search', '')
    if search:
        tests = tests.filter(name__icontains=search)

    paginator = Paginator(tests, 20)
    page = request.GET.get('page', 1)
    try:
        tests_page = paginator.page(page)
    except (EmptyPage, PageNotAnInteger):
        tests_page = paginator.page(1)

    return render(request, 'testing/list.html', {
        'tests': tests_page,
        'subjects': subjects,
        'current_subject': int(subject_id) if subject_id else None,
        'search': search,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def test_create(request):
    """Создание нового теста."""
    subjects = Subject.objects.all().order_by('full_name')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        subject_id = request.POST.get('subject')
        description = request.POST.get('description', '').strip()
        if not name:
            messages.error(request, 'Введите название теста.')
            return render(request, 'testing/create.html', {
                'subjects': subjects,
                'form_data': request.POST,
            })
        if not subject_id:
            messages.error(request, 'Выберите дисциплину.')
            return render(request, 'testing/create.html', {
                'subjects': subjects,
                'form_data': request.POST,
            })
        subject = get_object_or_404(Subject, id=subject_id)
        Test.objects.create(
            author=request.user,
            subject=subject,
            name=name,
            description=description or None,
        )
        messages.success(request, f'Тест «{name}» создан.')
        return redirect('testing:list')
    return render(request, 'testing/create.html', {
        'subjects': subjects,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def test_edit(request, test_id):
    """Редактирование теста."""
    test = get_object_or_404(Test, id=test_id)
    subjects = Subject.objects.all().order_by('full_name')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        subject_id = request.POST.get('subject')
        description = request.POST.get('description', '').strip()
        if not name:
            messages.error(request, 'Введите название теста.')
            return render(request, 'testing/create.html', {
                'subjects': subjects,
                'test': test,
                'form_data': request.POST,
                'editing': True,
            })
        if not subject_id:
            messages.error(request, 'Выберите дисциплину.')
            return render(request, 'testing/create.html', {
                'subjects': subjects,
                'test': test,
                'form_data': request.POST,
                'editing': True,
            })
        test.name = name
        test.subject_id = subject_id
        test.description = description or None
        test.save(update_fields=['name', 'subject', 'description'])
        messages.success(request, f'Тест «{name}» обновлён.')
        return redirect('testing:list')
    return render(request, 'testing/create.html', {
        'subjects': subjects,
        'test': test,
        'editing': True,
        'test_id': test.id,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def test_delete(request, test_id):
    """Удаление теста — перенос в архив."""
    test = get_object_or_404(Test.objects.prefetch_related('questions__choices'), id=test_id)
    if request.method == 'POST':
        # Экспортируем данные теста в JSON для сохранения в архиве
        questions_data = []
        for q in test.questions.all().order_by('order', 'id'):
            questions_data.append({
                'text': q.text,
                'question_type': q.question_type,
                'order': q.order,
                'score': q.score,
                'choices': [
                    {'text': c.text, 'is_correct': c.is_correct}
                    for c in q.choices.all()
                ],
            })
        export_data = json.dumps({
            'format': 'msudle-test-export-v1',
            'test': {
                'name': test.name,
                'description': test.description,
                'subject_id': test.subject_id,
                'subject_name': test.subject.full_name,
            },
            'questions': questions_data,
        }, ensure_ascii=False, indent=2)

        author_name = test.author.get_full_name() or test.author.get_username()
        DeletedTest.objects.create(
            original_id=test.id,
            author_id=test.author_id,
            author_name=author_name,
            subject_id=test.subject_id,
            subject_name=test.subject.full_name,
            name=test.name,
            description=test.description,
            export_data=export_data,
            created_at=test.created_at,
        )
        name = test.name
        test.delete()
        messages.success(request, f'Тест «{name}» перемещён в архив.')
        return redirect('testing:list')
    return render(request, 'testing/delete_confirm.html', {
        'test': test,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def test_archive_list(request):
    """Список удалённых тестов (архив)."""
    deleted = DeletedTest.objects.all()
    paginator = Paginator(deleted, 10)
    page = request.GET.get('page', 1)
    try:
        deleted_page = paginator.page(page)
    except (EmptyPage, PageNotAnInteger):
        deleted_page = paginator.page(1)
    return render(request, 'testing/archive_list.html', {
        'deleted_tests': deleted_page,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def test_archive_restore(request, deleted_id):
    """Восстановление теста из архива."""
    from django.contrib.auth.models import User
    deleted = get_object_or_404(DeletedTest, id=deleted_id)
    if request.method == 'POST':
        data = json.loads(deleted.export_data)
        questions_data = data.get('questions', [])
        test_data = data.get('test', {})

        # Ищем или создаём автора
        try:
            author = User.objects.get(id=deleted.author_id)
        except User.DoesNotExist:
            author = request.user

        # Ищем или создаём дисциплину
        try:
            subject = Subject.objects.get(id=deleted.subject_id)
        except Subject.DoesNotExist:
            subject = Subject.objects.first()

        test = Test.objects.create(
            author=author,
            subject=subject,
            name=deleted.name,
            description=deleted.description,
        )
        for qdata in questions_data:
            q = Question.objects.create(
                test=test,
                text=qdata.get('text', '').strip(),
                question_type=qdata.get('question_type', 'single'),
                order=qdata.get('order', 0),
                score=max(int(qdata.get('score', 1)), 1),
            )
            for cdata in qdata.get('choices', []):
                Choice.objects.create(
                    question=q,
                    text=cdata.get('text', '').strip(),
                    is_correct=bool(cdata.get('is_correct', False)),
                )

        name = deleted.name
        deleted.delete()
        messages.success(request, f'Тест «{name}» восстановлен из архива.')
        return redirect('testing:archive')

    return render(request, 'testing/archive_restore_confirm.html', {
        'deleted': deleted,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def test_archive_destroy(request, deleted_id):
    """Окончательное удаление теста из архива."""
    deleted = get_object_or_404(DeletedTest, id=deleted_id)
    if request.method == 'POST':
        name = deleted.name
        deleted.delete()
        messages.success(request, f'Тест «{name}» окончательно удалён.')
        return redirect('testing:archive')
    return render(request, 'testing/archive_destroy_confirm.html', {
        'deleted': deleted,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def test_preview(request, test_id):
    """Предпросмотр теста — преподаватель может пройти тест, результаты не сохраняются."""
    test = get_object_or_404(Test.objects.prefetch_related('questions__choices'), id=test_id)
    questions = list(test.questions.all())
    if not questions:
        messages.warning(request, 'В тесте нет вопросов. Добавьте вопросы через редактирование.')
        return redirect('testing:list')

    if request.method == 'POST':
        # Подсчёт результатов
        total_score = 0
        max_score = 0
        results = []
        for q in questions:
            max_score += q.score
            choice_ids = request.POST.getlist(f'q_{q.id}')
            chosen_ids = set(int(c) for c in choice_ids if c.isdigit())
            correct_ids = set(q.choices.filter(is_correct=True).values_list('id', flat=True))
            is_correct = chosen_ids == correct_ids
            if is_correct:
                total_score += q.score
            results.append({
                'question': q,
                'chosen_ids': chosen_ids,
                'correct_ids': correct_ids,
                'is_correct': is_correct,
            })
        return render(request, 'testing/preview.html', {
            'test': test,
            'questions': questions,
            'results': results,
            'total_score': total_score,
            'max_score': max_score,
            'submitted': True,
        })

    return render(request, 'testing/preview.html', {
        'test': test,
        'questions': questions,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def test_export(request, test_id):
    """Экспорт теста в JSON для резервного копирования."""
    test = get_object_or_404(Test.objects.prefetch_related('questions__choices'), id=test_id)
    questions_data = []
    for q in test.questions.all().order_by('order', 'id'):
        questions_data.append({
            'text': q.text,
            'question_type': q.question_type,
            'order': q.order,
            'score': q.score,
            'choices': [
                {'text': c.text, 'is_correct': c.is_correct}
                for c in q.choices.all()
            ],
        })

    export_data = {
        'format': 'msudle-test-export-v1',
        'test': {
            'name': test.name,
            'description': test.description,
            'subject_id': test.subject_id,
            'subject_name': test.subject.full_name,
        },
        'questions': questions_data,
    }

    response = HttpResponse(
        json.dumps(export_data, ensure_ascii=False, indent=2),
        content_type='application/json',
    )
    subject_name = test.subject.full_name.replace(' ', '_')
    test_name = test.name.replace(' ', '_')
    filename = f"test_{test_name}_{subject_name}.json"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def test_import(request):
    """Импорт теста из JSON-файла. Позволяет изменить название, дисциплину, описание."""
    subjects = Subject.objects.all().order_by('full_name')
    if request.method == 'POST':
        import_file = request.FILES.get('import_file')
        if not import_file:
            messages.error(request, 'Выберите файл для импорта.')
            return render(request, 'testing/import.html', {'subjects': subjects})

        try:
            raw = import_file.read().decode('utf-8-sig')
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            messages.error(request, f'Ошибка чтения файла: {e}')
            return render(request, 'testing/import.html', {'subjects': subjects})

        fmt = data.get('format', '')
        if fmt != 'msudle-test-export-v1':
            messages.error(request, 'Неверный формат файла. Ожидается msudle-test-export-v1.')
            return render(request, 'testing/import.html', {'subjects': subjects})

        test_data = data.get('test', {})
        questions_data = data.get('questions', [])

        name = request.POST.get('name', test_data.get('name', '')).strip()
        subject_id = request.POST.get('subject')
        description = request.POST.get('description', test_data.get('description', '')).strip()

        if not name:
            messages.error(request, 'Введите название теста.')
            return render(request, 'testing/import.html', {
                'subjects': subjects,
                'import_data': test_data,
                'questions_count': len(questions_data),
                'form_data': request.POST,
            })
        if not subject_id:
            messages.error(request, 'Выберите дисциплину.')
            return render(request, 'testing/import.html', {
                'subjects': subjects,
                'import_data': test_data,
                'questions_count': len(questions_data),
                'form_data': request.POST,
            })

        subject = get_object_or_404(Subject, id=subject_id)

        # Создаём тест
        test = Test.objects.create(
            author=request.user,
            subject=subject,
            name=name,
            description=description or None,
        )

        # Создаём вопросы
        for qdata in questions_data:
            q = Question.objects.create(
                test=test,
                text=qdata.get('text', '').strip(),
                question_type=qdata.get('question_type', 'single'),
                order=qdata.get('order', 0),
                score=max(int(qdata.get('score', 1)), 1),
            )
            for cdata in qdata.get('choices', []):
                Choice.objects.create(
                    question=q,
                    text=cdata.get('text', '').strip(),
                    is_correct=bool(cdata.get('is_correct', False)),
                )

        messages.success(request, f'Тест «{name}» импортирован ({len(questions_data)} вопросов).')
        return redirect('testing:list')

    # GET — показываем форму
    return render(request, 'testing/import.html', {'subjects': subjects, 'import_data': {}})
