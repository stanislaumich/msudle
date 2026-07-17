from django.db import models


class Shifr(models.Model):
    """Модель шифра (направления/специальности)."""
    code = models.CharField(max_length=20, verbose_name='Шифр', help_text='Пример: 6-05-0612-01, 1-40-01-01')
    name = models.CharField(max_length=300, null=True, blank=True, verbose_name='Название шифра')
    qualification = models.CharField(max_length=300, null=True, blank=True, verbose_name='Квалификация')

    class Meta:
        verbose_name = 'Шифр'
        verbose_name_plural = 'Шифры'

    def __str__(self):
        if self.name:
            return f'{self.code} ({self.name})'
        return self.code
