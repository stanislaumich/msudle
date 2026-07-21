from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from accounts.models import TeacherGroup
from .models import University, Faculty, Department


def _is_teacher(user):
    """Проверка: пользователь — сотрудник (User), а не студент."""
    return not hasattr(user, 'fio')


def _manage_dean_group(user, is_dean, new_is_dean):
    """Управление группой «Декан» / «Деканы» при назначении/смене декана."""
    dean_group, _ = Group.objects.get_or_create(name='Декан')
    dean_teacher_group, _ = TeacherGroup.objects.get_or_create(name='Деканы')
    if is_dean and not new_is_dean:
        # Бывший декан — удаляем из групп, если больше не декан нигде
        if not Faculty.objects.filter(dean=user).exists():
            user.groups.remove(dean_group)
            dean_teacher_group.users.remove(user)
    if new_is_dean and not is_dean:
        # Новый декан — добавляем в группы
        user.groups.add(dean_group)
        dean_teacher_group.users.add(user)


def _manage_head_group(user, is_head, new_is_head):
    """Управление группой «Заведующий кафедрой» при назначении/смене зав. кафедрой."""
    head_group, _ = Group.objects.get_or_create(name='Заведующий кафедрой')
    head_teacher_group, _ = TeacherGroup.objects.get_or_create(name='Заведующий кафедрой')
    if is_head and not new_is_head:
        # Бывший зав. кафедрой — удаляем из групп, если больше не зав. кафедрой нигде
        if not Department.objects.filter(head=user).exists():
            user.groups.remove(head_group)
            head_teacher_group.users.remove(user)
    if new_is_head and not is_head:
        # Новый зав. кафедрой — добавляем в группы
        user.groups.add(head_group)
        head_teacher_group.users.add(user)


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
    all_users = User.objects.filter(is_active=True).order_by('last_name', 'first_name')
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        short_name = request.POST.get('short_name', '').strip()
        university_id = request.POST.get('university')
        identifier = request.POST.get('identifier', '').strip() or None
        group_numbers = request.POST.get('group_numbers', '').strip() or None
        dean_id = request.POST.get('dean') or None

        if not full_name:
            messages.error(request, 'Введите полное наименование факультета.')
            return render(request, 'structure/faculty_form.html', {
                'universities': universities, 'all_users': all_users, 'form_data': request.POST,
            })
        if not short_name:
            short_name = full_name
        if not university_id:
            messages.error(request, 'Выберите университет.')
            return render(request, 'structure/faculty_form.html', {
                'universities': universities, 'all_users': all_users, 'form_data': request.POST,
            })

        university = get_object_or_404(University, id=university_id)
        dean_user = None
        if dean_id:
            try:
                dean_user = User.objects.get(id=int(dean_id))
            except (User.DoesNotExist, ValueError, TypeError):
                pass

        Faculty.objects.create(
            university=university,
            full_name=full_name,
            short_name=short_name,
            identifier=identifier,
            group_numbers=group_numbers,
            dean=dean_user,
        )
        if dean_user:
            _manage_dean_group(dean_user, is_dean=False, new_is_dean=True)
        messages.success(request, f'Факультет «{full_name}» создан.')
        return redirect('structure:dashboard')

    return render(request, 'structure/faculty_form.html', {
        'universities': universities, 'all_users': all_users,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def faculty_edit(request, faculty_id):
    """Редактирование факультета."""
    faculty = get_object_or_404(Faculty, id=faculty_id)
    universities = University.objects.all()
    all_users = User.objects.filter(is_active=True).order_by('last_name', 'first_name')
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        short_name = request.POST.get('short_name', '').strip()
        university_id = request.POST.get('university')
        identifier = request.POST.get('identifier', '').strip() or None
        group_numbers = request.POST.get('group_numbers', '').strip() or None
        dean_id = request.POST.get('dean') or None

        if not full_name:
            messages.error(request, 'Введите полное наименование факультета.')
            return render(request, 'structure/faculty_form.html', {
                'universities': universities, 'all_users': all_users, 'faculty': faculty, 'form_data': request.POST,
            })
        if not short_name:
            short_name = full_name
        if not university_id:
            messages.error(request, 'Выберите университет.')
            return render(request, 'structure/faculty_form.html', {
                'universities': universities, 'all_users': all_users, 'faculty': faculty, 'form_data': request.POST,
            })

        university = get_object_or_404(University, id=university_id)

        old_dean = faculty.dean
        new_dean_user = None
        if dean_id:
            try:
                new_dean_user = User.objects.get(id=int(dean_id))
            except (User.DoesNotExist, ValueError, TypeError):
                pass

        faculty.university = university
        faculty.full_name = full_name
        faculty.short_name = short_name
        faculty.identifier = identifier
        faculty.group_numbers = group_numbers
        faculty.dean = new_dean_user
        faculty.save()

        # Управление группой «Декан»
        if old_dean and old_dean != new_dean_user:
            _manage_dean_group(old_dean, is_dean=True, new_is_dean=False)
        if new_dean_user and new_dean_user != old_dean:
            _manage_dean_group(new_dean_user, is_dean=False, new_is_dean=True)

        messages.success(request, f'Факультет «{full_name}» обновлён.')
        return redirect('structure:dashboard')

    return render(request, 'structure/faculty_form.html', {
        'universities': universities, 'all_users': all_users, 'faculty': faculty,
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
    all_users = User.objects.filter(is_active=True).order_by('last_name', 'first_name')
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        short_name = request.POST.get('short_name', '').strip()
        faculty_id = request.POST.get('faculty')
        identifier = request.POST.get('identifier', '').strip() or None
        head_id = request.POST.get('head') or None

        if not full_name:
            messages.error(request, 'Введите полное наименование кафедры.')
            return render(request, 'structure/department_form.html', {
                'faculties': faculties, 'all_users': all_users, 'form_data': request.POST,
            })
        if not short_name:
            short_name = full_name
        if not faculty_id:
            messages.error(request, 'Выберите факультет.')
            return render(request, 'structure/department_form.html', {
                'faculties': faculties, 'all_users': all_users, 'form_data': request.POST,
            })

        faculty = get_object_or_404(Faculty, id=faculty_id)
        head_user = None
        if head_id:
            try:
                head_user = User.objects.get(id=int(head_id))
            except (User.DoesNotExist, ValueError, TypeError):
                pass

        Department.objects.create(
            faculty=faculty,
            full_name=full_name,
            short_name=short_name,
            identifier=identifier,
            head=head_user,
        )
        if head_user:
            _manage_head_group(head_user, is_head=False, new_is_head=True)
        messages.success(request, f'Кафедра «{full_name}» создана.')
        return redirect('structure:dashboard')

    return render(request, 'structure/department_form.html', {
        'faculties': faculties, 'all_users': all_users,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def department_edit(request, department_id):
    """Редактирование кафедры."""
    department = get_object_or_404(Department, id=department_id)
    faculties = Faculty.objects.select_related('university').all().order_by('university__full_name', 'full_name')
    all_users = User.objects.filter(is_active=True).order_by('last_name', 'first_name')
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        short_name = request.POST.get('short_name', '').strip()
        faculty_id = request.POST.get('faculty')
        identifier = request.POST.get('identifier', '').strip() or None
        head_id = request.POST.get('head') or None

        if not full_name:
            messages.error(request, 'Введите полное наименование кафедры.')
            return render(request, 'structure/department_form.html', {
                'faculties': faculties, 'all_users': all_users, 'department': department, 'form_data': request.POST,
            })
        if not short_name:
            short_name = full_name
        if not faculty_id:
            messages.error(request, 'Выберите факультет.')
            return render(request, 'structure/department_form.html', {
                'faculties': faculties, 'all_users': all_users, 'department': department, 'form_data': request.POST,
            })

        faculty = get_object_or_404(Faculty, id=faculty_id)

        old_head = department.head
        new_head_user = None
        if head_id:
            try:
                new_head_user = User.objects.get(id=int(head_id))
            except (User.DoesNotExist, ValueError, TypeError):
                pass

        department.faculty = faculty
        department.full_name = full_name
        department.short_name = short_name
        department.identifier = identifier
        department.head = new_head_user
        department.save()

        # Управление группой «Заведующий кафедрой»
        if old_head and old_head != new_head_user:
            _manage_head_group(old_head, is_head=True, new_is_head=False)
        if new_head_user and new_head_user != old_head:
            _manage_head_group(new_head_user, is_head=False, new_is_head=True)

        messages.success(request, f'Кафедра «{full_name}» обновлена.')
        return redirect('structure:dashboard')

    return render(request, 'structure/department_form.html', {
        'faculties': faculties, 'all_users': all_users, 'department': department,
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