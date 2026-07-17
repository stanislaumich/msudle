from django.db import models
from django.contrib.auth.models import User
from subject.models import Subject


class Test(models.Model):
    """Тест — набор вопросов, созданный преподавателем и привязанный к дисциплине."""
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='tests',
        verbose_name='Автор',
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='tests',
        verbose_name='Дисциплина',
    )
    name = models.CharField(max_length=300, verbose_name='Название теста')
    description = models.TextField(
        null=True,
        blank=True,
        verbose_name='Описание',
        help_text='Краткое описание теста (необязательно)',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата изменения')

    class Meta:
        verbose_name = 'Тест'
        verbose_name_plural = 'Тесты'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.subject.full_name})'