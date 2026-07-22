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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initial_dean = self.dean if self.pk else None

    def save(self, *args, **kwargs):
        old_dean = self._initial_dean
        new_dean = self.dean
        super().save(*args, **kwargs)
        self._sync_dean_group(old_dean, new_dean)
        self._initial_dean = new_dean  # обновляем кэш после сохранения

    def _sync_dean_group(self, old_dean, new_dean):
        from django.contrib.auth.models import Group as DjangoGroup
        from accounts.models import TeacherGroup
        if old_dean == new_dean:
            return
        dean_group, _ = DjangoGroup.objects.get_or_create(name='Декан')
        dean_teacher_group, _ = TeacherGroup.objects.get_or_create(name='Деканы')
        if old_dean and not Faculty.objects.filter(dean=old_dean).exists():
            old_dean.groups.remove(dean_group)
            dean_teacher_group.users.remove(old_dean)
        if new_dean:
            new_dean.groups.add(dean_group)
            dean_teacher_group.users.add(new_dean)

    def delete(self, *args, **kwargs):
        """При удалении факультета — снимаем декана с групп, если больше нигде не декан."""
        old_dean = self.dean
        super().delete(*args, **kwargs)
        if old_dean:
            from django.contrib.auth.models import Group as DjangoGroup
            from accounts.models import TeacherGroup
            if not Faculty.objects.filter(dean=old_dean).exists():
                dean_group = DjangoGroup.objects.filter(name='Декан').first()
                dean_teacher_group = TeacherGroup.objects.filter(name='Деканы').first()
                if dean_group:
                    old_dean.groups.remove(dean_group)
                if dean_teacher_group:
                    dean_teacher_group.users.remove(old_dean)

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initial_head = self.head if self.pk else None

    def save(self, *args, **kwargs):
        old_head = self._initial_head
        new_head = self.head
        super().save(*args, **kwargs)
        self._sync_head_group(old_head, new_head)
        self._initial_head = new_head  # обновляем кэш после сохранения

    def _sync_head_group(self, old_head, new_head):
        from django.contrib.auth.models import Group as DjangoGroup
        from accounts.models import TeacherGroup
        if old_head == new_head:
            return
        head_group, _ = DjangoGroup.objects.get_or_create(name='Заведующий кафедрой')
        head_teacher_group, _ = TeacherGroup.objects.get_or_create(name='Заведующий кафедрой')
        if old_head and not Department.objects.filter(head=old_head).exists():
            old_head.groups.remove(head_group)
            head_teacher_group.users.remove(old_head)
        if new_head:
            new_head.groups.add(head_group)
            head_teacher_group.users.add(new_head)

    def delete(self, *args, **kwargs):
        """При удалении кафедры — снимаем завкафедрой с групп, если больше нигде не зав."""
        old_head = self.head
        super().delete(*args, **kwargs)
        if old_head:
            from django.contrib.auth.models import Group as DjangoGroup
            from accounts.models import TeacherGroup
            if not Department.objects.filter(head=old_head).exists():
                head_group = DjangoGroup.objects.filter(name='Заведующий кафедрой').first()
                head_teacher_group = TeacherGroup.objects.filter(name='Заведующий кафедрой').first()
                if head_group:
                    old_head.groups.remove(head_group)
                if head_teacher_group:
                    head_teacher_group.users.remove(old_head)

    def __str__(self):
        return self.full_name
