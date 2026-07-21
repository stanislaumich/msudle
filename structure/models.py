from django.db import models
from django.contrib.auth.models import User


class University(models.Model):
    """Модель университета — корень структуры."""
    full_name = models.CharField(max_length=500, verbose_name='Полное наименование')
    short_name = models.CharField(max_length=100, verbose_name='Краткое наименование')
    identifier = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Идентификатор',
        help_text='Для внутренних нужд, не отображается в интерфейсе',
    )

    class Meta:
        verbose_name = 'Университет'
        verbose_name_plural = 'Университеты'

    def __str__(self):
        return self.full_name


class Faculty(models.Model):
    """Модель факультета — ссылается на университет."""
    university = models.ForeignKey(
        University,
        on_delete=models.CASCADE,
        related_name='faculties',
        verbose_name='Университет',
    )
    full_name = models.CharField(max_length=500, verbose_name='Полное наименование')
    short_name = models.CharField(max_length=100, verbose_name='Краткое наименование')
    identifier = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Идентификатор',
        help_text='Для внутренних нужд, не отображается в интерфейсе',
    )
    dean = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='faculties_as_dean',
        verbose_name='Декан',
    )
    group_numbers = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        verbose_name='Номера групп',
        help_text='Через запятую: первые цифры номеров групп этого факультета, например: 1,2,3',
    )

    class Meta:
        verbose_name = 'Факультет'
        verbose_name_plural = 'Факультеты'

    def __str__(self):
        return self.full_name


class Department(models.Model):
    """Модель кафедры — ссылается на факультет."""
    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.CASCADE,
        related_name='departments',
        verbose_name='Факультет',
    )
    full_name = models.CharField(max_length=500, verbose_name='Полное наименование')
    short_name = models.CharField(max_length=100, verbose_name='Краткое наименование')
    identifier = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Идентификатор',
        help_text='Для внутренних нужд, не отображается в интерфейсе',
    )
    head = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='departments_as_head',
        verbose_name='Заведующий кафедрой',
    )

    class Meta:
        verbose_name = 'Кафедра'
        verbose_name_plural = 'Кафедры'

    def __str__(self):
        return self.full_name
