from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import IntegrityError
from .models import Student, StudentGroup, DeletedStudent


def login_view(request):
    """Универсальная авторизация через все доступные бэкенды."""
    if request.method == 'POST':
        login_val = request.POST.get('login', '').strip()
        password = request.POST.get('password', '')

        # Django вызывает authenticate() на всех бэкендах по очереди
        # и сохраняет путь к бэкенду, который вернул пользователя.
        # Поэтому передаём login как username для EmailOrUsernameBackend
        # и как login для StudentBackend (оба параметра через **kwargs).
        user_obj = authenticate(
            request,
            username=login_val,
            login=login_val,
            password=password,
        )
        if user_obj is not None:
            auth_login(request, user_obj)
            display_name = _get_display_name(user_obj)
            messages.success(request, f'Добро пожаловать, {display_name}!')
            # Сотрудники/админы — на страницу курсов, студенты — на главную
            if hasattr(user_obj, 'fio'):
                return redirect('student_home')
            return redirect('home')
        else:
            messages.error(request, 'Неверный логин или пароль.')
    return redirect('index')


def logout_view(request):
    """Выход из системы."""
    auth_logout(request)
    messages.info(request, 'Вы вышли из системы.')
    return redirect('index')


def _get_display_name(user_obj):
    """Возвращает отображаемое имя пользователя."""
    if hasattr(user_obj, 'fio'):
        return user_obj.fio
    if user_obj.get_full_name():
        return user_obj.get_full_name()
    return user_obj.get_username()


def _is_teacher(user):
    """Проверка: пользователь — сотрудник (User), а не студент."""
    return not hasattr(user, 'fio')


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def student_list(request):
    """Список студентов с фильтрацией и поиском."""
    groups = StudentGroup.objects.all().order_by('group_number', 'subgroup_number')
    students = Student.objects.select_related('group').order_by('fio')

    group_id = request.GET.get('group')
    if group_id:
        students = students.filter(group_id=group_id)

    search = request.GET.get('search', '')
    if search:
        students = students.filter(fio__icontains=search) | students.filter(login__icontains=search)

    paginator = Paginator(students, 30)
    page = request.GET.get('page', 1)
    try:
        students_page = paginator.page(page)
    except (EmptyPage, PageNotAnInteger):
        students_page = paginator.page(1)

    return render(request, 'students/list.html', {
        'students': students_page,
        'groups': groups,
        'current_group': int(group_id) if group_id else None,
        'search': search,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def student_create(request):
    """Создание нового студента."""
    groups = StudentGroup.objects.all().order_by('group_number', 'subgroup_number')
    if request.method == 'POST':
        fio = request.POST.get('fio', '').strip()
        login_val = request.POST.get('login', '').strip()
        password = request.POST.get('password', '')
        group_id = request.POST.get('group')
        record_book = request.POST.get('record_book_number', '').strip()

        errors = []
        if not fio:
            errors.append('Введите ФИО студента.')
        if not login_val:
            errors.append('Введите логин.')
        elif Student.objects.filter(login=login_val).exists():
            errors.append('Студент с таким логином уже существует.')
        if not password:
            errors.append('Введите пароль.')
        if not group_id:
            errors.append('Выберите группу.')

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'students/create.html', {
                'groups': groups,
                'form_data': request.POST,
            })

        group = get_object_or_404(StudentGroup, id=group_id)
        student = Student.objects.create(
            fio=fio,
            login=login_val,
            group=group,
            record_book_number=record_book,
        )
        student.set_password(password)
        student.save()
        messages.success(request, f'Студент «{fio}» создан.')
        return redirect('students:list')

    return render(request, 'students/create.html', {
        'groups': groups,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def student_edit(request, student_id):
    """Редактирование студента."""
    student = get_object_or_404(Student, id=student_id)
    groups = StudentGroup.objects.all().order_by('group_number', 'subgroup_number')
    if request.method == 'POST':
        fio = request.POST.get('fio', '').strip()
        login_val = request.POST.get('login', '').strip()
        password = request.POST.get('password', '')
        group_id = request.POST.get('group')
        record_book = request.POST.get('record_book_number', '').strip()

        errors = []
        if not fio:
            errors.append('Введите ФИО студента.')
        if not login_val:
            errors.append('Введите логин.')
        elif Student.objects.filter(login=login_val).exclude(id=student_id).exists():
            errors.append('Студент с таким логином уже существует.')
        if not group_id:
            errors.append('Выберите группу.')

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'students/create.html', {
                'groups': groups,
                'student': student,
                'form_data': request.POST,
            })

        group = get_object_or_404(StudentGroup, id=group_id)
        student.fio = fio
        student.login = login_val
        student.group = group
        student.record_book_number = record_book
        if password:
            student.set_password(password)
        student.save()
        messages.success(request, f'Данные студента «{fio}» обновлены.')
        return redirect('students:list')

    return render(request, 'students/create.html', {
        'groups': groups,
        'student': student,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def student_delete(request, student_id):
    """Удаление студента."""
    student = get_object_or_404(Student, id=student_id)
    if request.method == 'POST':
        name = student.fio
        student.delete()
        messages.success(request, f'Студент «{name}» удалён.')
        return redirect('students:list')
    return render(request, 'students/delete_confirm.html', {
        'student': student,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def student_soft_delete(request, student_id):
    """Мягкое удаление студента: копия сохраняется в DeletedStudent, оригинал удаляется."""
    student = get_object_or_404(Student, id=student_id)
    if request.method == 'POST':
        # Сохраняем копию в архив
        DeletedStudent.objects.create(
            original_id=student.id,
            fio=student.fio,
            login=student.login,
            record_book_number=student.record_book_number,
            password=student.password,
            group_name=str(student.group) if student.group else '',
            last_login=student.last_login,
        )
        name = student.fio
        group_id = student.group_id
        student.delete()
        messages.success(request, f'Студент «{name}» перемещён в архив.')
        if group_id:
            return redirect('students:group_edit', group_id=group_id)
        return redirect('students:group_list')
    # GET — показать подтверждение
    return render(request, 'students/delete_confirm.html', {
        'student': student,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def group_list(request):
    """Список групп студентов."""
    from structure.models import Faculty
    groups = StudentGroup.objects.select_related('shifr', 'faculty').order_by('group_number', 'subgroup_number')

    faculty_id = request.GET.get('faculty')
    if faculty_id:
        groups = groups.filter(faculty_id=faculty_id)

    group_search = request.GET.get('group_search', '').strip()
    if group_search:
        groups = groups.filter(group_number__icontains=group_search)

    faculties = Faculty.objects.all().order_by('full_name')
    current_faculty_label = ''
    if faculty_id:
        try:
            current_faculty_label = str(faculties.get(id=faculty_id))
        except Faculty.DoesNotExist:
            pass

    return render(request, 'students/group_list.html', {
        'groups': groups,
        'faculties': faculties,
        'current_faculty': faculty_id,
        'current_faculty_label': current_faculty_label,
        'group_search': group_search,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def group_create(request):
    """Создание новой группы."""
    from umo.models import Shifr
    from structure.models import Faculty
    shifrs = Shifr.objects.all().order_by('code')
    faculties = Faculty.objects.all().order_by('full_name')
    if request.method == 'POST':
        group_number = request.POST.get('group_number', '').strip()
        subgroup_number = request.POST.get('subgroup_number', '').strip()
        shifr_id = request.POST.get('shifr') or None
        enrollment_year = request.POST.get('enrollment_year', '').strip()
        study_duration_years = request.POST.get('study_duration_years', '').strip()
        study_duration_months = request.POST.get('study_duration_months', '').strip()
        faculty_id = request.POST.get('faculty') or None
        education_form = request.POST.get('education_form', '').strip()

        if not group_number:
            messages.error(request, 'Введите номер группы.')
            return render(request, 'students/group_create.html', {
                'shifrs': shifrs, 'faculties': faculties, 'form_data': request.POST,
            })

        subgroup = int(subgroup_number) if subgroup_number else None
        # Проверка уникальности
        if StudentGroup.objects.filter(group_number=group_number, subgroup_number=subgroup).exists():
            messages.error(request, 'Группа с таким номером и подгруппой уже существует.')
            return render(request, 'students/group_create.html', {
                'shifrs': shifrs, 'faculties': faculties, 'form_data': request.POST,
            })

        group = StudentGroup.objects.create(
            group_number=group_number,
            subgroup_number=subgroup,
            shifr_id=shifr_id,
            enrollment_year=int(enrollment_year) if enrollment_year else None,
            study_duration_years=int(study_duration_years) if study_duration_years else None,
            study_duration_months=int(study_duration_months) if study_duration_months else None,
            faculty_id=faculty_id,
            education_form=education_form or None,
        )
        messages.success(request, f'Группа «{group}» создана.')
        return redirect('students:group_list')

    return render(request, 'students/group_create.html', {
        'shifrs': shifrs,
        'faculties': faculties,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def group_edit(request, group_id):
    """Редактирование группы."""
    from umo.models import Shifr
    from structure.models import Faculty
    group = get_object_or_404(StudentGroup, id=group_id)
    shifrs = Shifr.objects.all().order_by('code')
    faculties = Faculty.objects.all().order_by('full_name')
    if request.method == 'POST':
        group_number = request.POST.get('group_number', '').strip()
        subgroup_number = request.POST.get('subgroup_number', '').strip()
        shifr_id = request.POST.get('shifr') or None
        enrollment_year = request.POST.get('enrollment_year', '').strip()
        study_duration_years = request.POST.get('study_duration_years', '').strip()
        study_duration_months = request.POST.get('study_duration_months', '').strip()
        faculty_id = request.POST.get('faculty') or None
        education_form = request.POST.get('education_form', '').strip()

        if not group_number:
            messages.error(request, 'Введите номер группы.')
            return render(request, 'students/group_create.html', {
                'shifrs': shifrs, 'faculties': faculties, 'group': group, 'form_data': request.POST,
            })

        subgroup = int(subgroup_number) if subgroup_number else None
        if StudentGroup.objects.filter(group_number=group_number, subgroup_number=subgroup).exclude(id=group_id).exists():
            messages.error(request, 'Группа с таким номером и подгруппой уже существует.')
            return render(request, 'students/group_create.html', {
                'shifrs': shifrs, 'faculties': faculties, 'group': group, 'form_data': request.POST,
            })

        group.group_number = group_number
        group.subgroup_number = subgroup
        group.shifr_id = shifr_id
        group.enrollment_year = int(enrollment_year) if enrollment_year else None
        group.study_duration_years = int(study_duration_years) if study_duration_years else None
        group.study_duration_months = int(study_duration_months) if study_duration_months else None
        group.faculty_id = faculty_id
        group.education_form = education_form or None
        group.save()
        messages.success(request, f'Группа «{group}» обновлена.')
        return redirect('students:group_list')

    students = group.students.all().order_by('fio')
    shifr_label = str(group.shifr) if group.shifr else ''
    return render(request, 'students/group_create.html', {
        'shifrs': shifrs,
        'faculties': faculties,
        'group': group,
        'students': students,
        'shifr_label': shifr_label,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def archive_list(request):
    """Список удалённых студентов (архив) с пагинацией по 10."""
    deleted = DeletedStudent.objects.all()
    paginator = Paginator(deleted, 10)
    page = request.GET.get('page', 1)
    try:
        deleted_page = paginator.page(page)
    except (EmptyPage, PageNotAnInteger):
        deleted_page = paginator.page(1)
    return render(request, 'students/archive_list.html', {
        'deleted_students': deleted_page,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def archive_restore(request, deleted_id):
    """Восстановление удалённого студента из архива."""
    deleted = get_object_or_404(DeletedStudent, id=deleted_id)
    if request.method == 'POST':
        # Проверяем, не занят ли логин
        if Student.objects.filter(login=deleted.login).exists():
            messages.error(request, f'Невозможно восстановить: логин «{deleted.login}» уже занят.')
            return redirect('students:archive')
        try:
            student = Student.objects.create(
                id=deleted.original_id,
                fio=deleted.fio,
                login=deleted.login,
                record_book_number=deleted.record_book_number,
                password=deleted.password,
                last_login=deleted.last_login,
            )
        except IntegrityError:
            # ID занят — создаём с авто-ID
            student = Student.objects.create(
                fio=deleted.fio,
                login=deleted.login,
                record_book_number=deleted.record_book_number,
                password=deleted.password,
                last_login=deleted.last_login,
            )
        name = deleted.fio
        deleted.delete()
        messages.success(request, f'Студент «{name}» восстановлен из архива.')
        return redirect('students:archive')
    return render(request, 'students/archive_restore_confirm.html', {
        'deleted': deleted,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/students/login/')
def group_delete(request, group_id):
    """Удаление группы."""
    group = get_object_or_404(StudentGroup, id=group_id)
    if request.method == 'POST':
        name = str(group)
        group.delete()
        messages.success(request, f'Группа «{name}» удалена.')
        return redirect('students:group_list')
    return render(request, 'students/group_delete_confirm.html', {
        'group': group,
    })
