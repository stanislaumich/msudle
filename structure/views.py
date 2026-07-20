from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import University, Faculty, Department


def _is_teacher(user):
    """Проверка: пользователь — сотрудник (User), а не студент."""
    return not hasattr(user, 'fio')


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def structure_dashboard(request):
    """Панель управления структурой: университет, факультеты, кафедры."""
    universities = University.objects.prefetch_related('faculties__departments').all()
    return render(request, 'structure/dashboard.html', {
        'universities': universities,
    })


# --- Факультеты ---

@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def faculty_create(request):
    """Создание факультета."""
    universities = University.objects.all()
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        short_name = request.POST.get('short_name', '').strip()
        university_id = request.POST.get('university')
        identifier = request.POST.get('identifier', '').strip() or None

        if not full_name:
            messages.error(request, 'Введите полное наименование факультета.')
            return render(request, 'structure/faculty_form.html', {
                'universities': universities, 'form_data': request.POST,
            })
        if not short_name:
            short_name = full_name
        if not university_id:
            messages.error(request, 'Выберите университет.')
            return render(request, 'structure/faculty_form.html', {
                'universities': universities, 'form_data': request.POST,
            })

        university = get_object_or_404(University, id=university_id)
        Faculty.objects.create(
            university=university,
            full_name=full_name,
            short_name=short_name,
            identifier=identifier,
        )
        messages.success(request, f'Факультет «{full_name}» создан.')
        return redirect('structure:dashboard')

    return render(request, 'structure/faculty_form.html', {
        'universities': universities,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def faculty_edit(request, faculty_id):
    """Редактирование факультета."""
    faculty = get_object_or_404(Faculty, id=faculty_id)
    universities = University.objects.all()
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        short_name = request.POST.get('short_name', '').strip()
        university_id = request.POST.get('university')
        identifier = request.POST.get('identifier', '').strip() or None

        if not full_name:
            messages.error(request, 'Введите полное наименование факультета.')
            return render(request, 'structure/faculty_form.html', {
                'universities': universities, 'faculty': faculty, 'form_data': request.POST,
            })
        if not short_name:
            short_name = full_name
        if not university_id:
            messages.error(request, 'Выберите университет.')
            return render(request, 'structure/faculty_form.html', {
                'universities': universities, 'faculty': faculty, 'form_data': request.POST,
            })

        university = get_object_or_404(University, id=university_id)
        faculty.university = university
        faculty.full_name = full_name
        faculty.short_name = short_name
        faculty.identifier = identifier
        faculty.save()
        messages.success(request, f'Факультет «{full_name}» обновлён.')
        return redirect('structure:dashboard')

    return render(request, 'structure/faculty_form.html', {
        'universities': universities, 'faculty': faculty,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def faculty_delete(request, faculty_id):
    """Удаление факультета."""
    faculty = get_object_or_404(Faculty, id=faculty_id)
    if request.method == 'POST':
        name = faculty.full_name
        faculty.delete()
        messages.success(request, f'Факультет «{name}» удалён.')
        return redirect('structure:dashboard')
    return render(request, 'structure/delete_confirm.html', {
        'obj': faculty, 'type': 'факультет', 'cancel_url': 'structure:dashboard',
    })


# --- Кафедры ---

@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def department_create(request):
    """Создание кафедры."""
    faculties = Faculty.objects.select_related('university').all().order_by('university__full_name', 'full_name')
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        short_name = request.POST.get('short_name', '').strip()
        faculty_id = request.POST.get('faculty')
        identifier = request.POST.get('identifier', '').strip() or None

        if not full_name:
            messages.error(request, 'Введите полное наименование кафедры.')
            return render(request, 'structure/department_form.html', {
                'faculties': faculties, 'form_data': request.POST,
            })
        if not short_name:
            short_name = full_name
        if not faculty_id:
            messages.error(request, 'Выберите факультет.')
            return render(request, 'structure/department_form.html', {
                'faculties': faculties, 'form_data': request.POST,
            })

        faculty = get_object_or_404(Faculty, id=faculty_id)
        Department.objects.create(
            faculty=faculty,
            full_name=full_name,
            short_name=short_name,
            identifier=identifier,
        )
        messages.success(request, f'Кафедра «{full_name}» создана.')
        return redirect('structure:dashboard')

    return render(request, 'structure/department_form.html', {
        'faculties': faculties,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def department_edit(request, department_id):
    """Редактирование кафедры."""
    department = get_object_or_404(Department, id=department_id)
    faculties = Faculty.objects.select_related('university').all().order_by('university__full_name', 'full_name')
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        short_name = request.POST.get('short_name', '').strip()
        faculty_id = request.POST.get('faculty')
        identifier = request.POST.get('identifier', '').strip() or None

        if not full_name:
            messages.error(request, 'Введите полное наименование кафедры.')
            return render(request, 'structure/department_form.html', {
                'faculties': faculties, 'department': department, 'form_data': request.POST,
            })
        if not short_name:
            short_name = full_name
        if not faculty_id:
            messages.error(request, 'Выберите факультет.')
            return render(request, 'structure/department_form.html', {
                'faculties': faculties, 'department': department, 'form_data': request.POST,
            })

        faculty = get_object_or_404(Faculty, id=faculty_id)
        department.faculty = faculty
        department.full_name = full_name
        department.short_name = short_name
        department.identifier = identifier
        department.save()
        messages.success(request, f'Кафедра «{full_name}» обновлена.')
        return redirect('structure:dashboard')

    return render(request, 'structure/department_form.html', {
        'faculties': faculties, 'department': department,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def university_edit(request, university_id):
    """Редактирование университета."""
    university = get_object_or_404(University, id=university_id)
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        short_name = request.POST.get('short_name', '').strip()
        identifier = request.POST.get('identifier', '').strip() or None

        if not full_name:
            messages.error(request, 'Введите полное наименование университета.')
            return render(request, 'structure/university_form.html', {
                'university': university, 'form_data': request.POST,
            })
        if not short_name:
            short_name = full_name

        university.full_name = full_name
        university.short_name = short_name
        university.identifier = identifier
        university.save()
        messages.success(request, f'Университет «{full_name}» обновлён.')
        return redirect('structure:dashboard')

    return render(request, 'structure/university_form.html', {
        'university': university,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def department_delete(request, department_id):
    """Удаление кафедры."""
    department = get_object_or_404(Department, id=department_id)
    if request.method == 'POST':
        name = department.full_name
        department.delete()
        messages.success(request, f'Кафедра «{name}» удалена.')
        return redirect('structure:dashboard')
    return render(request, 'structure/delete_confirm.html', {
        'obj': department, 'type': 'кафедру', 'cancel_url': 'structure:dashboard',
    })