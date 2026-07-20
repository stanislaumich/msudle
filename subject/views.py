from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render, redirect, get_object_or_404
from .models import Subject
from structure.models import Faculty, Department


def _is_teacher(user):
    """Проверка: пользователь — сотрудник (User), а не студент."""
    return not hasattr(user, 'fio')


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def subject_list(request):
    """Список дисциплин с фильтрацией по факультету и кафедре."""
    faculties = Faculty.objects.all().order_by('full_name')
    departments = Department.objects.select_related('faculty').all().order_by('faculty__full_name', 'full_name')
    subjects = Subject.objects.select_related('department__faculty').order_by('full_name')

    # Фильтр по факультету
    faculty_id = request.GET.get('faculty')
    if faculty_id:
        subjects = subjects.filter(department__faculty_id=faculty_id)
        departments = departments.filter(faculty_id=faculty_id)

    # Фильтр по кафедре
    department_id = request.GET.get('department')
    if department_id:
        subjects = subjects.filter(department_id=department_id)

    # Поиск по названию
    search = request.GET.get('search', '')
    if search:
        subjects = subjects.filter(full_name__icontains=search)

    paginator = Paginator(subjects, 20)
    page = request.GET.get('page', 1)
    try:
        subjects_page = paginator.page(page)
    except (EmptyPage, PageNotAnInteger):
        subjects_page = paginator.page(1)

    return render(request, 'subject/list.html', {
        'subjects': subjects_page,
        'faculties': faculties,
        'departments': departments,
        'current_faculty': int(faculty_id) if faculty_id else None,
        'current_department': int(department_id) if department_id else None,
        'search': search,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def subject_create(request):
    """Создание новой дисциплины."""
    departments = Department.objects.select_related('faculty').all().order_by('faculty__full_name', 'full_name')
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        short_name = request.POST.get('short_name', '').strip()
        department_id = request.POST.get('department')
        identifier = request.POST.get('identifier', '').strip() or None
        if not full_name:
            messages.error(request, 'Введите полное наименование дисциплины.')
            return render(request, 'subject/create.html', {
                'departments': departments,
                'form_data': request.POST,
            })
        if not short_name:
            messages.error(request, 'Введите краткое наименование дисциплины.')
            return render(request, 'subject/create.html', {
                'departments': departments,
                'form_data': request.POST,
            })
        if not department_id:
            messages.error(request, 'Выберите кафедру.')
            return render(request, 'subject/create.html', {
                'departments': departments,
                'form_data': request.POST,
            })
        department = get_object_or_404(Department, id=department_id)
        Subject.objects.create(
            department=department,
            full_name=full_name,
            short_name=short_name,
            identifier=identifier,
        )
        messages.success(request, f'Дисциплина «{full_name}» создана.')
        return redirect('subject:list')
    return render(request, 'subject/create.html', {
        'departments': departments,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def subject_edit(request, subject_id):
    """Редактирование дисциплины."""
    subject = get_object_or_404(Subject, id=subject_id)
    departments = Department.objects.select_related('faculty').all().order_by('faculty__full_name', 'full_name')
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        short_name = request.POST.get('short_name', '').strip()
        department_id = request.POST.get('department')
        identifier = request.POST.get('identifier', '').strip() or None
        if not full_name:
            messages.error(request, 'Введите полное наименование дисциплины.')
            return render(request, 'subject/create.html', {
                'departments': departments,
                'subject': subject,
                'form_data': request.POST,
                'editing': True,
            })
        if not short_name:
            messages.error(request, 'Введите краткое наименование дисциплины.')
            return render(request, 'subject/create.html', {
                'departments': departments,
                'subject': subject,
                'form_data': request.POST,
                'editing': True,
            })
        if not department_id:
            messages.error(request, 'Выберите кафедру.')
            return render(request, 'subject/create.html', {
                'departments': departments,
                'subject': subject,
                'form_data': request.POST,
                'editing': True,
            })
        subject.full_name = full_name
        subject.short_name = short_name
        subject.department_id = department_id
        subject.identifier = identifier
        subject.save(update_fields=['full_name', 'short_name', 'department', 'identifier'])
        messages.success(request, f'Дисциплина «{full_name}» обновлена.')
        return redirect('subject:list')
    return render(request, 'subject/create.html', {
        'departments': departments,
        'subject': subject,
        'editing': True,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def subject_delete(request, subject_id):
    """Удаление дисциплины."""
    subject = get_object_or_404(Subject, id=subject_id)
    if request.method == 'POST':
        name = subject.full_name
        subject.delete()
        messages.success(request, f'Дисциплина «{name}» удалена.')
        return redirect('subject:list')
    return render(request, 'subject/delete_confirm.html', {
        'subject': subject,
    })