from django.contrib.auth.backends import BaseBackend, ModelBackend
from .models import Student


class StudentBackend(BaseBackend):
    """Бэкенд аутентификации для студентов (модель Student)."""

    def authenticate(self, request, login=None, password=None, **kwargs):
        if login is None or password is None:
            return None
        try:
            student = Student.objects.get(login=login)
        except Student.DoesNotExist:
            return None
        if student.check_password(password):
            return student
        return None

    def get_user(self, user_id):
        try:
            return Student.objects.get(pk=user_id)
        except Student.DoesNotExist:
            return None


class EmailOrUsernameBackend(ModelBackend):
    """
    Бэкенд для Django User.
    Аутентифицирует по username ИЛИ email (стандартный ModelBackend работает только по username).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        if username is None or password is None:
            return None

        # Пробуем найти пользователя по username
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # Пробуем найти по email
            try:
                user = User.objects.get(email=username)
            except User.DoesNotExist:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None