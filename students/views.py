from django.shortcuts import redirect
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
from django.contrib import messages


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