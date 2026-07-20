from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import Shifr
from structure.models import Faculty

def is_staff_user(user):
    return user.is_authenticated and not hasattr(user, 'fio')

def shifr_list(request):
    """Список всех шифров с фильтрацией по факультету."""
    faculty_id = request.GET.get('faculty', '')
    faculties = Faculty.objects.all()
    shifrs = Shifr.objects.select_related('faculty').order_by('code')

    if faculty_id:
        shifrs = shifrs.filter(faculty_id=faculty_id)

    return render(request, 'umo/shifr_list.html', {
        'shifrs': shifrs,
        'faculties': faculties,
        'selected_faculty': int(faculty_id) if faculty_id else None,
    })

@user_passes_test(is_staff_user)
def shifr_create(request):
    """Создание нового шифра."""
    faculties = Faculty.objects.all()
    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        name = request.POST.get('name', '').strip()
        qualification = request.POST.get('qualification', '').strip()
        faculty_id = request.POST.get('faculty', '')

        if not code:
            messages.error(request, 'Шифр обязателен для заполнения.')
            return render(request, 'umo/shifr_form.html', {
                'faculties': faculties,
                'form_data': {'code': code, 'name': name, 'qualification': qualification, 'faculty': faculty_id},
            })

        shifr = Shifr(
            code=code,
            name=name or None,
            qualification=qualification or None,
            faculty_id=int(faculty_id) if faculty_id else None,
        )
        shifr.save()
        messages.success(request, f'Шифр {code} успешно создан.')
        return redirect('umo:shifr_list')

    return render(request, 'umo/shifr_form.html', {'faculties': faculties})

@user_passes_test(is_staff_user)
def shifr_edit(request, pk):
    """Редактирование шифра."""
    shifr = get_object_or_404(Shifr, pk=pk)
    faculties = Faculty.objects.all()

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        name = request.POST.get('name', '').strip()
        qualification = request.POST.get('qualification', '').strip()
        faculty_id = request.POST.get('faculty', '')

        if not code:
            messages.error(request, 'Шифр обязателен для заполнения.')
            return render(request, 'umo/shifr_form.html', {
                'shifr': shifr,
                'faculties': faculties,
                'form_data': {'code': code, 'name': name, 'qualification': qualification, 'faculty': faculty_id},
            })

        shifr.code = code
        shifr.name = name or None
        shifr.qualification = qualification or None
        shifr.faculty_id = int(faculty_id) if faculty_id else None
        shifr.save()
        messages.success(request, f'Шифр {code} успешно обновлён.')
        return redirect('umo:shifr_list')

    return render(request, 'umo/shifr_form.html', {'shifr': shifr, 'faculties': faculties})

@user_passes_test(is_staff_user)
def shifr_delete(request, pk):
    """Удаление шифра."""
    shifr = get_object_or_404(Shifr, pk=pk)
    if request.method == 'POST':
        code = shifr.code
        shifr.delete()
        messages.success(request, f'Шифр {code} успешно удалён.')
        return redirect('umo:shifr_list')

    return render(request, 'umo/shifr_delete_confirm.html', {'shifr': shifr})