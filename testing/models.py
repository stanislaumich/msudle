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


class Question(models.Model):
    """Вопрос теста."""
    QUESTION_TYPE_CHOICES = [
        ('single', 'Одиночный выбор'),
        ('multiple', 'Множественный выбор'),
    ]

    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name='Тест',
    )
    text = models.TextField(verbose_name='Текст вопроса')
    question_type = models.CharField(
        max_length=10,
        choices=QUESTION_TYPE_CHOICES,
        default='single',
        verbose_name='Тип вопроса',
    )
    order = models.PositiveSmallIntegerField(default=0, verbose_name='Порядок')
    score = models.PositiveSmallIntegerField(
        default=1,
        verbose_name='Балл за правильный ответ',
        help_text='Сколько баллов получает студент за правильный ответ на этот вопрос',
    )

    class Meta:
        verbose_name = 'Вопрос'
        verbose_name_plural = 'Вопросы'
        ordering = ['order', 'id']

    def __str__(self):
        return f'Вопрос {self.order}: {self.text[:80]}'


class Choice(models.Model):
    """Вариант ответа к вопросу."""
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='choices',
        verbose_name='Вопрос',
    )
    text = models.CharField(max_length=500, verbose_name='Текст варианта')
    is_correct = models.BooleanField(default=False, verbose_name='Правильный')

    class Meta:
        verbose_name = 'Вариант ответа'
        verbose_name_plural = 'Варианты ответов'
        ordering = ['id']

    def __str__(self):
        prefix = '✓ ' if self.is_correct else '  '
        return f'{prefix}{self.text[:80]}'