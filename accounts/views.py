import json
import random

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User

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
