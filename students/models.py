from django.contrib.auth.hashers import make_password, check_password
from django.db import models


class StudentGroup(models.Model):
    """Модель группы студентов."""
    group_number = models.CharField(max_length=50, verbose_name='Номер группы')
    shifr = models.ForeignKey(
        'umo.Shifr',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='groups',
        verbose_name='Код специальности',
    )
    enrollment_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name='Год поступления',
        help_text='Начало обучения',
    )
    study_duration_years = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name='Срок обучения (лет)',
    )
    study_duration_months = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name='Срок обучения (месяцев)',
    )
    faculty = models.ForeignKey(
        'structure.Faculty',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_groups',
        verbose_name='Факультет',
    )
    education_form = models.CharField(
        max_length=20,
        choices=[
            ('daytime', 'Дневная'),
            ('correspondence', 'Заочная'),
        ],
        null=True,
        blank=True,
        verbose_name='Форма получения образования',
    )

    class Meta:
        verbose_name = 'Группа студентов'
        verbose_name_plural = 'Группы студентов'
        unique_together = ()

    def __str__(self):
        return str(self.group_number)


class Student(models.Model):
    """Модель студента."""
    fio = models.CharField(max_length=300, verbose_name='ФИО')
    group = models.ForeignKey(
        StudentGroup,
        on_delete=models.CASCADE,
        related_name='students',
        verbose_name='Группа',
        null=True,
        blank=True,
    )
    login = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Логин',
        help_text='Используется для входа в систему',
        default='',
    )
    record_book_number = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name='Номер зачётной книжки',
        help_text='Необязательное поле',
    )
    password = models.CharField(max_length=128, verbose_name='Пароль (хэш)', default='')
    last_login = models.DateTimeField(null=True, blank=True, verbose_name='Последний вход')

    class Meta:
        verbose_name = 'Студент'
        verbose_name_plural = 'Студенты'

    def __str__(self):
        return self.fio

    def set_password(self, raw_password):
        """Хэширует и сохраняет пароль."""
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        """Проверяет пароль."""
        return check_password(raw_password, self.password)

    # --- Свойства для совместимости с Django auth system ---

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_username(self):
        return self.login

    def get_full_name(self):
        return self.fio


class DeletedStudent(models.Model):
    """Архив удалённых студентов (для возможности восстановления)."""
    original_id = models.PositiveIntegerField(verbose_name='ID оригинального студента')
    fio = models.CharField(max_length=300, verbose_name='ФИО')
    login = models.CharField(max_length=100, verbose_name='Логин')
    record_book_number = models.CharField(
        max_length=50, blank=True, default='', verbose_name='Номер зачётной книжки',
    )
    password = models.CharField(max_length=128, verbose_name='Пароль (хэш)')
    group_id = models.PositiveIntegerField(null=True, blank=True, verbose_name='ID группы')
    group_name = models.CharField(max_length=100, verbose_name='Группа')
    last_login = models.DateTimeField(null=True, blank=True, verbose_name='Последний вход')
    deleted_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата удаления')

    class Meta:
        verbose_name = 'Удалённый студент'
        verbose_name_plural = 'Удалённые студенты'
        ordering = ['-deleted_at']

    def __str__(self):
        return f'{self.fio} (удалён {self.deleted_at.strftime("%d.%m.%Y")})'
