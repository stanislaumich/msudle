from django.db import models
from django.contrib.auth.models import User


class TeacherGroup(models.Model):
    """Группа преподавателей (M2M — один преподаватель может быть в нескольких группах)."""
    name = models.CharField(max_length=300, verbose_name='Название группы')
    users = models.ManyToManyField(
        User,
        related_name='teacher_groups',
        blank=True,
        verbose_name='Преподаватели',
    )

    class Meta:
        verbose_name = 'Группа преподавателей'
        verbose_name_plural = 'Группы преподавателей'

    def __str__(self):
        cnt = self.users.count()
        return f'{self.name} ({cnt} чел.)'
