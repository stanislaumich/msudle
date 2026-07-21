import csv
import io
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from .models import Shifr
from structure.models import Faculty

def is_staff_user(user):
    return user.is_authenticated and not hasattr(user, 'fio')

def shifr_list(request):
    """Список всех кодов специальностей с фильтрацией по факультету."""
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
    """Создание нового кода специальности."""
    faculties = Faculty.objects.all()
    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        name = request.POST.get('name', '').strip()
        qualification = request.POST.get('qualification', '').strip()
        faculty_id = request.POST.get('faculty', '')

        if not code:
            messages.error(request, 'Код обязателен для заполнения.')
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
        messages.success(request, f'Код {code} успешно создан.')
        return redirect('umo:shifr_list')

    return render(request, 'umo/shifr_form.html', {'faculties': faculties})

@user_passes_test(is_staff_user)
def shifr_edit(request, pk):
    """Редактирование кода специальности."""
    shifr = get_object_or_404(Shifr, pk=pk)
    faculties = Faculty.objects.all()

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        name = request.POST.get('name', '').strip()
        qualification = request.POST.get('qualification', '').strip()
        faculty_id = request.POST.get('faculty', '')

        if not code:
            messages.error(request, 'Код обязателен для заполнения.')
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
        messages.success(request, f'Код {code} успешно обновлён.')
        return redirect('umo:shifr_list')

    return render(request, 'umo/shifr_form.html', {'shifr': shifr, 'faculties': faculties})

@user_passes_test(is_staff_user)
def shifr_delete(request, pk):
    """Удаление кода специальности."""
    shifr = get_object_or_404(Shifr, pk=pk)
    if request.method == 'POST':
        code = shifr.code
        shifr.delete()
        messages.success(request, f'Код {code} успешно удалён.')
        return redirect('umo:shifr_list')

    return render(request, 'umo/shifr_delete_confirm.html', {'shifr': shifr})


@user_passes_test(is_staff_user)
def shifr_export(request):
    """Экспорт всех кодов в CSV."""
    shifrs = Shifr.objects.select_related('faculty').order_by('code')
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['code', 'name', 'qualification', 'faculty_name'])
    for s in shifrs:
        writer.writerow([
            s.code,
            s.name or '',
            s.qualification or '',
            s.faculty.full_name if s.faculty else '',
        ])
    response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="shifry_export.csv"'
    return response


@user_passes_test(is_staff_user)
def shifr_import_full(request):
    """Полный импорт кодов — удаляет все старые и загружает из CSV/JSON."""
    faculties = Faculty.objects.all()
    if request.method == 'POST':
        import_file = request.FILES.get('import_file')
        if not import_file:
            messages.error(request, 'Выберите файл для импорта.')
            return render(request, 'umo/shifr_import.html', {'faculties': faculties, 'mode': 'full'})

        data = _parse_shifr_file(import_file)
        if data is None:
            messages.error(request, 'Неверный формат файла. Ожидается CSV (code,name,qualification,faculty_name) или JSON.')
            return render(request, 'umo/shifr_import.html', {'faculties': faculties, 'mode': 'full'})

        # Удаляем все существующие
        count_before = Shifr.objects.count()
        Shifr.objects.all().delete()

        _import_shifrs(data, faculties)
        messages.success(request, f'Импорт завершён. Удалено: {count_before}, загружено: {len(data)}.')
        return redirect('umo:shifr_list')

    return render(request, 'umo/shifr_import.html', {'faculties': faculties, 'mode': 'full'})


@user_passes_test(is_staff_user)
def shifr_import_partial(request):
    """Частичный импорт — добавляет новые, обновляет квалификацию и название у существующих."""
    faculties = Faculty.objects.all()
    if request.method == 'POST':
        import_file = request.FILES.get('import_file')
        if not import_file:
            messages.error(request, 'Выберите файл для импорта.')
            return render(request, 'umo/shifr_import.html', {'faculties': faculties, 'mode': 'partial'})

        data = _parse_shifr_file(import_file)
        if data is None:
            messages.error(request, 'Неверный формат файла. Ожидается CSV (code,name,qualification,faculty_name) или JSON.')
            return render(request, 'umo/shifr_import.html', {'faculties': faculties, 'mode': 'partial'})

        created = 0
        updated = 0
        # Строим индекс существующих кодов
        existing = {s.code: s for s in Shifr.objects.all()}
        # Строим индекс факультетов
        faculty_index = {f.full_name: f for f in faculties}

        for row in data:
            code = row.get('code', '').strip()
            if not code:
                continue
            name = row.get('name', '').strip()
            qualification = row.get('qualification', '').strip()
            faculty_name = row.get('faculty_name', '').strip()
            faculty = faculty_index.get(faculty_name)

            if code in existing:
                s = existing[code]
                s.name = name or s.name
                s.qualification = qualification or s.qualification
                if faculty:
                    s.faculty = faculty
                s.save(update_fields=['name', 'qualification', 'faculty'])
                updated += 1
            else:
                Shifr.objects.create(
                    code=code,
                    name=name or None,
                    qualification=qualification or None,
                    faculty=faculty,
                )
                created += 1

        messages.success(request, f'Импорт завершён. Добавлено: {created}, обновлено: {updated}.')
        return redirect('umo:shifr_list')

    return render(request, 'umo/shifr_import.html', {'faculties': faculties, 'mode': 'partial'})


def _parse_shifr_file(import_file):
    """Разбирает CSV или JSON файл в список словарей [{code, name, qualification, faculty_name}]."""
    raw = import_file.read()
    # Пробуем JSON
    try:
        data = json.loads(raw.decode('utf-8-sig'))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    # Пробуем CSV
    try:
        content = raw.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content), delimiter=';')
        rows = []
        for r in reader:
            rows.append({
                'code': r.get('code', '').strip(),
                'name': r.get('name', '').strip(),
                'qualification': r.get('qualification', '').strip(),
                'faculty_name': r.get('faculty_name', '').strip(),
            })
        if rows:
            return rows
    except Exception:
        pass

    return None


def _import_shifrs(data, faculties):
    """Создаёт Shifr из списка словарей."""
    faculty_index = {f.full_name: f for f in faculties}
    for row in data:
        code = row.get('code', '').strip()
        if not code:
            continue
        faculty_name = row.get('faculty_name', '').strip()
        faculty = faculty_index.get(faculty_name)
        Shifr.objects.create(
            code=code,
            name=row.get('name', '').strip() or None,
            qualification=row.get('qualification', '').strip() or None,
            faculty=faculty,
        )
