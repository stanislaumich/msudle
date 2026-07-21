from django.db import models
from structure.models import Faculty


class Shifr(models.Model):
    """Модель кода специальности (направления/специальности)."""
    code = models.CharField(max_length=20, verbose_name='Код', help_text='Пример: 6-05-0612-01, 1-40-01-01')
    name = models.CharField(max_length=300, null=True, blank=True, verbose_name='Название')
    qualification = models.CharField(max_length=300, null=True, blank=True, verbose_name='Квалификация')
    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shifrs',
        verbose_name='Факультет',
        help_text='Факультет, к которому относится данный код специальности',
    )

    class Meta:
        verbose_name = 'Код специальности'
        verbose_name_plural = 'Коды специальностей'

    def __str__(self):
        if self.name:
            return f'{self.code} ({self.name})'
        return self.code
