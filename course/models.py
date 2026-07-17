import os
import random
import re
import string

from django.db import models
from django.contrib.auth.models import User, Group


def _safe_dirname(name):
    """Преобразует строку в безопасное имя папки: транслит, только буквы/цифры/дефис."""
    # Простейшая транслитерация кириллицы
    translit = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
        'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
        'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
    }
    result = ''.join(translit.get(ch, ch) for ch in name)
    # Заменяем всё кроме букв, цифр и дефиса на дефис
    result = re.sub(r'[^a-zA-Z0-9\-]', '-', result)
    # Убираем множественные дефисы и крайние
    result = re.sub(r'-+', '-', result).strip('-')
    return result.lower() if result else 'unnamed'


def learning_unit_upload_to(instance, filename):
    """Формирует путь: data/{faculty}/{department}/{course}/{filename}
    Использует identifier или короткое название вместо числовых ID."""
    if instance.topic:
        course = instance.topic.section.course
    else:
        course = instance.section.course
    department = course.subject.department
    faculty = department.faculty

    # Имя папки факультета: identifier или full_name
    faculty_dir = faculty.identifier if faculty.identifier else _safe_dirname(faculty.full_name)
    # Имя папки кафедры: identifier или full_name
    dept_dir = department.identifier if department.identifier else _safe_dirname(department.full_name)
    # Имя папки курса: identifier или short_name
    course_dir = course.identifier if course.identifier else _safe_dirname(course.short_name)

    return os.path.join('data', faculty_dir, dept_dir, course_dir, filename)


class Course(models.Model):
    """Модель курса обучения."""
    subject = models.ForeignKey(
        'subject.Subject',
        on_delete=models.CASCADE,
        related_name='courses',
        verbose_name='Предмет',
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
        verbose_name = 'Курс'
        verbose_name_plural = 'Курсы'

    def __str__(self):
        return self.short_name


class CourseUserPermission(models.Model):
    """Права пользователя на курс."""
    PERMISSION_CHOICES = [
        ('edit', 'Редактирование'),
        ('create_delete', 'Создание и удаление'),
        ('view', 'Только просмотр'),
        ('full_access', 'Полный доступ'),
    ]

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='user_permissions',
        verbose_name='Курс',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='course_permissions',
        verbose_name='Пользователь',
    )
    permission = models.CharField(
        max_length=20,
        choices=PERMISSION_CHOICES,
        verbose_name='Уровень доступа',
    )

    class Meta:
        verbose_name = 'Права пользователя на курс'
        verbose_name_plural = 'Права пользователей на курсы'
        unique_together = ('course', 'user')

    def __str__(self):
        return f'{self.user} — {self.course} ({self.get_permission_display()})'


class CourseGroupPermission(models.Model):
    """Права группы пользователей на курс."""
    PERMISSION_CHOICES = [
        ('edit', 'Редактирование'),
        ('create_delete', 'Создание и удаление'),
        ('view', 'Только просмотр'),
        ('full_access', 'Полный доступ'),
    ]

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='group_permissions',
        verbose_name='Курс',
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='course_permissions',
        verbose_name='Группа',
    )
    permission = models.CharField(
        max_length=20,
        choices=PERMISSION_CHOICES,
        verbose_name='Уровень доступа',
    )

    class Meta:
        verbose_name = 'Права группы на курс'
        verbose_name_plural = 'Права групп на курсы'
        unique_together = ('course', 'group')

    def __str__(self):
        return f'{self.group} — {self.course} ({self.get_permission_display()})'


class CourseSection(models.Model):
    """Раздел курса — промежуточный уровень группировки занятий."""

    DEFAULT_SECTIONS = [
        'Пояснительный',
        'Теоретический',
        'Практический',
        'Контрольный',
        'Вспомогательный',
        'Преподавательский',
    ]

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='sections',
        verbose_name='Курс',
    )
    name = models.CharField(max_length=200, verbose_name='Название раздела')
    order = models.PositiveSmallIntegerField(default=0, verbose_name='Порядок')
    visible = models.BooleanField(
        default=True,
        verbose_name='Видим студентам',
        help_text='Если выключено, раздел скрыт от студентов',
    )

    class Meta:
        verbose_name = 'Раздел курса'
        verbose_name_plural = 'Разделы курсов'
        ordering = ['order', 'id']
        unique_together = ('course', 'name')

    def __str__(self):
        return f'{self.name} ({self.course.short_name})'


class CourseTopic(models.Model):
    """Тема внутри раздела курса — единица содержания."""

    section = models.ForeignKey(
        CourseSection,
        on_delete=models.CASCADE,
        related_name='topics',
        verbose_name='Раздел',
    )
    entity_title = models.CharField(
        max_length=100,
        verbose_name='Название сущности',
        help_text='Как пользователь называет эту единицу: «Тема», «Параграф», «Лекция» и т.п.',
    )
    content = models.CharField(
        max_length=500,
        verbose_name='Содержание',
        help_text='Собственно название темы, например «Введение в программирование»',
    )
    order = models.PositiveSmallIntegerField(default=0, verbose_name='Порядок')
    visible = models.BooleanField(
        default=True,
        verbose_name='Видима студентам',
        help_text='Если выключено, тема скрыта от студентов',
    )

    class Meta:
        verbose_name = 'Тема раздела'
        verbose_name_plural = 'Темы разделов'
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.entity_title}: {self.content}'


class LearningUnit(models.Model):
    """Единица обучения внутри темы — файл или ссылка на активность."""

    CONTENT_TYPE_CHOICES = [
        ('methodical', 'Методическая единица'),
        ('lecture', 'Лекционная единица'),
        ('control', 'Контрольная единица'),
    ]

    GRADING_TYPE_CHOICES = [
        ('pass_fail', 'Зачтено / не зачтено'),
        ('score_100', 'Баллы'),
    ]

    topic = models.ForeignKey(
        CourseTopic,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='units',
        verbose_name='Тема',
    )
    section = models.ForeignKey(
        CourseSection,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='direct_units',
        verbose_name='Раздел',
        help_text='Если единица привязана напрямую к разделу без темы',
    )
    title = models.CharField(max_length=300, verbose_name='Название единицы')
    content_type = models.CharField(
        max_length=30,
        choices=CONTENT_TYPE_CHOICES,
        default='file',
        verbose_name='Тип содержимого',
    )
    file = models.FileField(
        upload_to=learning_unit_upload_to,
        null=True,
        blank=True,
        verbose_name='Файл',
        help_text='Загружаемый файл: PDF, DOC, DOCX, JPG и т.д.',
    )
    link = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name='Ссылка',
        help_text='Ссылка на внешний ресурс или внутренний модуль',
    )
    order = models.PositiveSmallIntegerField(default=0, verbose_name='Порядок')
    visible = models.BooleanField(
        default=True,
        verbose_name='Видима студентам',
        help_text='Если выключено, единица скрыта от студентов',
    )
    grading_type = models.CharField(
        max_length=20,
        choices=GRADING_TYPE_CHOICES,
        null=True,
        blank=True,
        verbose_name='Тип оценки',
        help_text='Только для контрольных единиц. Укажите способ оценивания.',
    )
    test = models.ForeignKey(
        'testing.Test',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='learning_units',
        verbose_name='Тест',
        help_text='Прикрепить тест для прохождения студентом (только для контрольных единиц).',
    )
    max_score = models.PositiveSmallIntegerField(
        default=10,
        verbose_name='Максимальный балл',
        help_text='Максимальный балл за эту контрольную единицу (по умолчанию 10).',
    )

    class Meta:
        verbose_name = 'Единица обучения'
        verbose_name_plural = 'Единицы обучения'
        ordering = ['order', 'id']

    def filename(self):
        """Возвращает только имя файла без пути."""
        if self.file:
            return os.path.basename(self.file.name)
        return ''

    def __str__(self):
        return self.title


class CourseGroupStudent(models.Model):
    """Прикреплённая группа студентов к курсу."""
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='group_students',
        verbose_name='Курс',
    )
    group = models.ForeignKey(
        'students.StudentGroup',
        on_delete=models.CASCADE,
        related_name='courses',
        verbose_name='Группа',
        null=True,
    )

    class Meta:
        verbose_name = 'Группа студентов курса'
        verbose_name_plural = 'Группы студентов курсов'
        unique_together = ('course', 'group')

    def __str__(self):
        return f'{self.course.short_name} — {self.group}'


def student_answer_upload_to(instance, filename):
    """Формирует путь: answers/{faculty}/{department}/{course}/{login}_{random}.ext"""
    course = instance.learning_unit.topic.section.course if instance.learning_unit.topic else instance.learning_unit.section.course
    department = course.subject.department
    faculty = department.faculty
    faculty_dir = faculty.identifier if faculty.identifier else _safe_dirname(faculty.full_name)
    dept_dir = department.identifier if department.identifier else _safe_dirname(department.full_name)
    course_dir = course.identifier if course.identifier else _safe_dirname(course.short_name)
    ext = os.path.splitext(filename)[1]
    random_suffix = ''.join(random.choices(string.digits, k=5))
    safe_login = re.sub(r'[^a-zA-Z0-9\-]', '-', instance.student.login).strip('-').lower() or 'student'
    new_filename = f'{safe_login}_{random_suffix}{ext}'
    return os.path.join('answers', faculty_dir, dept_dir, course_dir, new_filename)


class StudentAnswer(models.Model):
    """Ответ студента на контрольную единицу."""
    GRADING_CHOICES = [
        ('pass_fail', 'Зачтено / не зачтено'),
        ('score_100', 'Баллы'),
    ]

    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name='Студент',
    )
    learning_unit = models.ForeignKey(
        LearningUnit,
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name='Контрольная единица',
        limit_choices_to={'content_type': 'control'},
    )
    answer_file = models.FileField(
        upload_to=student_answer_upload_to,
        null=True,
        blank=True,
        verbose_name='Файл ответа',
        help_text='Загруженный студентом файл',
    )
    answer_text = models.TextField(
        null=True,
        blank=True,
        verbose_name='Текст ответа',
    )
    checked = models.BooleanField(
        default=False,
        verbose_name='Проверена',
        help_text='Преподаватель проверил работу',
    )
    score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name='Балл',
        help_text='Оценка (например, 0–100)',
    )
    passed = models.BooleanField(
        null=True,
        blank=True,
        verbose_name='Зачтено',
        help_text='Зачтено / не зачтено',
    )
    comment = models.TextField(
        null=True,
        blank=True,
        verbose_name='Комментарий преподавателя',
        help_text='Текстовый комментарий к оценке',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата ответа',
    )
    modified_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата изменения ответа',
    )
    checked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Дата проверки',
    )
    checked_modified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Дата изменения проверки',
    )

    class Meta:
        verbose_name = 'Ответ студента'
        verbose_name_plural = 'Ответы студентов'
        unique_together = ('student', 'learning_unit')

    def __str__(self):
        return f'{self.student.login} — {self.learning_unit.title}'


class CourseAnnouncement(models.Model):
    """Объявление по курсу — отображается студентам и преподавателям."""
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='announcements',
        verbose_name='Курс',
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name='Автор',
    )
    text = models.TextField(
        verbose_name='Текст объявления',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата публикации',
    )

    class Meta:
        verbose_name = 'Объявление курса'
        verbose_name_plural = 'Объявления курсов'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.course.short_name}: {self.text[:60]}'

    def is_dismissed_by(self, user):
        """Проверяет, скрыл ли пользователь (User или Student) это объявление."""
        from students.models import Student
        if isinstance(user, Student):
            return self.dismissals.filter(student=user).exists()
        return self.dismissals.filter(user=user).exists()


class AnnouncementDismiss(models.Model):
    """Персональное скрытие объявления (студент или преподаватель)."""
    announcement = models.ForeignKey(
        CourseAnnouncement,
        on_delete=models.CASCADE,
        related_name='dismissals',
        verbose_name='Объявление',
    )
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='dismissed_announcements',
        verbose_name='Студент',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='dismissed_announcements',
        verbose_name='Пользователь',
    )
    dismissed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата скрытия',
    )

    class Meta:
        verbose_name = 'Скрытие объявления'
        verbose_name_plural = 'Скрытия объявлений'
        constraints = [
            models.UniqueConstraint(
                fields=['announcement', 'user'],
                name='unique_dismiss_user',
                condition=models.Q(user__isnull=False),
            ),
            models.UniqueConstraint(
                fields=['announcement', 'student'],
                name='unique_dismiss_student',
                condition=models.Q(student__isnull=False),
            ),
        ]

    def __str__(self):
        who = self.user.get_username() if self.user else (self.student.fio if self.student else '?')
        return f'{who} скрыл "{self.announcement.text[:40]}"'