import json
import random

from django.db import models as django_models
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404

from .models import TeacherGroup

# ---------- Транслитерация ----------

TRANSLIT_DICT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'А': 'a', 'Б': 'b', 'В': 'v', 'Г': 'g', 'Д': 'd', 'Е': 'e', 'Ё': 'e',
    'Ж': 'zh', 'З': 'z', 'И': 'i', 'Й': 'y', 'К': 'k', 'Л': 'l', 'М': 'm',
    'Н': 'n', 'О': 'o', 'П': 'p', 'Р': 'r', 'С': 's', 'Т': 't', 'У': 'u',
    'Ф': 'f', 'Х': 'kh', 'Ц': 'ts', 'Ч': 'ch', 'Ш': 'sh', 'Щ': 'shch',
    'Ъ': '', 'Ы': 'y', 'Ь': '', 'Э': 'e', 'Ю': 'yu', 'Я': 'ya',
}


def translit(text):
    result = []
    for ch in text:
        result.append(TRANSLIT_DICT.get(ch, ch))
    return ''.join(result)


def generate_login(full_name, exclude_pk=None):
    if not full_name:
        return None
    parts = full_name.strip().split()
    initials = ''.join(part[0] for part in parts if part)
    translit_initials = translit(initials).lower()
    if not translit_initials:
        return None
    qs = User.objects.filter(username__startswith=translit_initials)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    for _ in range(100):
        number = str(random.randint(100, 999))
        candidate = f'{translit_initials}{number}'
        if not qs.filter(username=candidate).exists():
            return candidate
    number = str(random.randint(1000, 9999))
    return f'{translit_initials}{number}'


@csrf_exempt
@require_POST
def generate_login_view(request):
    """API: принимает full_name, возвращает сгенерированный логин."""
    try:
        data = json.loads(request.body)
        full_name = data.get('full_name', '').strip()
    except json.JSONDecodeError:
        full_name = request.POST.get('full_name', '').strip()

    if not full_name:
        return JsonResponse({'success': False, 'error': 'full_name is required'}, status=400)

    login = generate_login(full_name)
    if login:
        return JsonResponse({'success': True, 'login': login})
    return JsonResponse({'success': False, 'error': 'could not generate'}, status=400)


# ---------- Teacher Groups ----------

def _is_teacher(user):
    return not hasattr(user, 'fio')


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def teacher_group_list(request):
    """Список групп преподавателей."""
    groups = TeacherGroup.objects.all().order_by('name')
    return render(request, 'accounts/teacher_groups.html', {'groups': groups})


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def teacher_group_edit(request, group_id):
    """Редактирование группы: название и участники."""
    group = get_object_or_404(TeacherGroup, id=group_id)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Введите название группы.')
            return redirect('accounts:teacher_group_edit', group_id=group.id)

        group.name = name
        group.save(update_fields=['name'])

        # Обновляем участников
        user_ids = request.POST.getlist('user_ids')
        group.users.set(user_ids)
        messages.success(request, f'Группа «{name}» обновлена ({group.users.count()} чел.).')
        return redirect('accounts:teacher_groups')

    all_users = User.objects.filter(is_active=True).order_by('last_name', 'first_name')
    current_ids = set(group.users.values_list('id', flat=True))
    return render(request, 'accounts/teacher_group_edit.html', {
        'group': group,
        'all_users': all_users,
        'current_ids': current_ids,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def teacher_group_create(request):
    """Создание новой группы преподавателей."""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Введите название группы.')
            return redirect('accounts:teacher_groups')

        group = TeacherGroup.objects.create(name=name)
        user_ids = request.POST.getlist('user_ids')
        if user_ids:
            group.users.set(user_ids)
        messages.success(request, f'Группа «{name}» создана ({group.users.count()} чел.).')
        return redirect('accounts:teacher_groups')

    all_users = User.objects.filter(is_active=True).order_by('last_name', 'first_name')
    return render(request, 'accounts/teacher_group_edit.html', {
        'all_users': all_users,
        'current_ids': set(),
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def teacher_group_delete(request, group_id):
    """Удаление группы преподавателей."""
    group = get_object_or_404(TeacherGroup, id=group_id)
    if request.method == 'POST':
        name = group.name
        group.delete()
        messages.success(request, f'Группа «{name}» удалена.')
        return redirect('accounts:teacher_groups')
    return render(request, 'accounts/teacher_group_delete.html', {'group': group})


# ---------- Teachers CRUD ----------

@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def teacher_list(request):
    """Список преподавателей."""
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    users_qs = User.objects.filter(is_active=True).order_by('last_name', 'first_name')
    search = request.GET.get('search', '')
    if search:
        users_qs = users_qs.filter(
            django_models.Q(first_name__icontains=search) |
            django_models.Q(last_name__icontains=search) |
            django_models.Q(username__icontains=search)
        )
    paginator = Paginator(users_qs, 20)
    page = request.GET.get('page', 1)
    try:
        users_page = paginator.page(page)
    except (EmptyPage, PageNotAnInteger):
        users_page = paginator.page(1)

    groups = TeacherGroup.objects.all().order_by('name')
    return render(request, 'accounts/teacher_list.html', {
        'users': users_page,
        'search': search,
        'groups': groups,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def teacher_create(request):
    """Создание преподавателя."""
    groups = TeacherGroup.objects.all().order_by('name')
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        group_ids = request.POST.getlist('group_ids')

        if not first_name or not last_name:
            messages.error(request, 'Имя и фамилия обязательны.')
            return render(request, 'accounts/teacher_form.html', {
                'groups': groups, 'form_data': request.POST,
            })
        if not username:
            # Генерируем логин
            username = generate_login(f'{last_name} {first_name}')
            if not username:
                messages.error(request, 'Не удалось сгенерировать логин. Введите вручную.')
                return render(request, 'accounts/teacher_form.html', {
                    'groups': groups, 'form_data': request.POST,
                })
        if User.objects.filter(username=username).exists():
            messages.error(request, f'Логин «{username}» уже занят.')
            return render(request, 'accounts/teacher_form.html', {
                'groups': groups, 'form_data': request.POST,
            })
        if not password:
            from django.utils.crypto import get_random_string
            password = get_random_string(12)

        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        user.is_staff = True
        user.save(update_fields=['is_staff'])

        if group_ids:
            user.teacher_groups.set(group_ids)

        messages.success(request, f'Преподаватель «{last_name} {first_name}» создан (логин: {username}).')
        return redirect('accounts:teacher_list')

    return render(request, 'accounts/teacher_form.html', {
        'groups': groups, 'teacher': None, 'current_group_ids': set(),
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def teacher_edit(request, user_id):
    """Редактирование преподавателя."""
    user = get_object_or_404(User, id=user_id)
    groups = TeacherGroup.objects.all().order_by('name')
    current_group_ids = set(user.teacher_groups.values_list('id', flat=True))

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        group_ids = request.POST.getlist('group_ids')

        if not first_name or not last_name:
            messages.error(request, 'Имя и фамилия обязательны.')
            return render(request, 'accounts/teacher_form.html', {
                'teacher': user, 'groups': groups, 'current_group_ids': current_group_ids,
                'form_data': request.POST,
            })
        if not username:
            messages.error(request, 'Логин обязателен.')
            return render(request, 'accounts/teacher_form.html', {
                'teacher': user, 'groups': groups, 'current_group_ids': current_group_ids,
                'form_data': request.POST,
            })
        if User.objects.filter(username=username).exclude(id=user.id).exists():
            messages.error(request, f'Логин «{username}» уже занят.')
            return render(request, 'accounts/teacher_form.html', {
                'teacher': user, 'groups': groups, 'current_group_ids': current_group_ids,
                'form_data': request.POST,
            })

        user.first_name = first_name
        user.last_name = last_name
        user.username = username
        if password:
            user.set_password(password)
        user.save()

        user.teacher_groups.set(group_ids)
        messages.success(request, f'Преподаватель «{last_name} {first_name}» обновлён.')
        return redirect('accounts:teacher_list')

    return render(request, 'accounts/teacher_form.html', {
        'teacher': user, 'groups': groups, 'current_group_ids': current_group_ids,
    })


@login_required
@user_passes_test(_is_teacher, login_url='/home/')
def teacher_delete(request, user_id):
    """Удаление преподавателя."""
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        name = user.get_full_name() or user.get_username()
        user.delete()
        messages.success(request, f'Преподаватель «{name}» удалён.')
        return redirect('accounts:teacher_list')
    return render(request, 'accounts/teacher_delete.html', {'teacher': user})
