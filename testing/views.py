from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render, redirect, get_object_or_404
from .models import Test
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
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def test_delete(request, test_id):
    """Удаление теста."""
    test = get_object_or_404(Test, id=test_id)
    if request.method == 'POST':
        name = test.name
        test.delete()
        messages.success(request, f'Тест «{name}» удалён.')
        return redirect('testing:list')
    return render(request, 'testing/delete_confirm.html', {
        'test': test,
    })