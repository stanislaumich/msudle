from django.db import models


class Subject(models.Model):
    """Модель дисциплины (предмета) учебного заведения."""
    department = models.ForeignKey(
        'structure.Department',
        on_delete=models.CASCADE,
        related_name='subjects',
        verbose_name='Кафедра',
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

    class Meta:
        verbose_name = 'Дисциплина'
        verbose_name_plural = 'Дисциплины'

    def __str__(self):
        return self.full_name
