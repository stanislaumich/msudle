from django.db import models
from django.contrib.auth.models import User


class ChatRoom(models.Model):
    """
    Комната чата между преподавателем и студентом в рамках курса.
    unique_together: (course, student) — одна комната на пару курс-студент.
    """
    course = models.ForeignKey(
        'course.Course',
        on_delete=models.CASCADE,
        related_name='chat_rooms',
        verbose_name='Курс',
    )
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='chat_rooms',
        verbose_name='Студент',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания',
    )
    is_deleted = models.BooleanField(
        default=False,
        verbose_name='Удалена (софт)',
        help_text='Если включено, комната помечена как удалённая и не отображается в списке.',
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Дата удаления',
    )

    class Meta:
        verbose_name = 'Комната чата'
        verbose_name_plural = 'Комнаты чатов'
        unique_together = ('course', 'student')
        ordering = ['-created_at']

    def __str__(self):
        prefix = '[Удалён] ' if self.is_deleted else ''
        return f'{prefix}{self.course.short_name} — {self.student.fio}'

    def unread_count_for(self, user):
        """Количество непрочитанных сообщений для пользователя."""
        if hasattr(user, 'fio'):
            # Студент — непрочитанные от преподавателей
            return self.messages.filter(is_read=False, sender_user__isnull=False).count()
        else:
            # Преподаватель — непрочитанные от студента
            return self.messages.filter(is_read=False, sender_student__isnull=False).count()

    def last_message(self):
        return self.messages.order_by('-created_at').first()


class GroupChat(models.Model):
    """
    Групповой чат для студентов одной группы.
    Одна комната на группу (OneToOne).
    """
    group = models.OneToOneField(
        'students.StudentGroup',
        on_delete=models.CASCADE,
        related_name='group_chat',
        verbose_name='Группа',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания',
    )

    class Meta:
        verbose_name = 'Групповой чат'
        verbose_name_plural = 'Групповые чаты'
        ordering = ['-created_at']

    def __str__(self):
        return f'Чат группы {self.group.group_number}'

    def last_message(self):
        return self.messages.order_by('-created_at').first()

    def unread_count_for(self, student):
        """Количество непрочитанных сообщений для студента.
        Прочитанные отслеживаем через флаг is_read — все сообщения,
        отправленные другими студентами, которые ещё не прочитаны.
        """
        # Студент читает: непрочитанные сообщения от других студентов
        return self.messages.filter(is_read=False).exclude(sender_student=student).count()


class GroupChatMessage(models.Model):
    """Сообщение в групповом чате."""
    room = models.ForeignKey(
        GroupChat,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Комната',
    )
    sender_student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='group_chat_messages',
        verbose_name='Отправитель',
    )
    text = models.TextField(
        verbose_name='Текст сообщения',
    )
    is_read = models.BooleanField(
        default=False,
        verbose_name='Прочитано',
        help_text='Помечается после того, как все студенты группы прочитали (для простоты — не используется активно).',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата отправки',
    )

    class Meta:
        verbose_name = 'Сообщение группового чата'
        verbose_name_plural = 'Сообщения групповых чатов'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.sender_student.fio}: {self.text[:50]}'


class ChatMessage(models.Model):
    """Сообщение в чате."""
    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Комната',
    )
    sender_student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='chat_messages',
        verbose_name='Отправитель-студент',
    )
    sender_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='chat_messages',
        verbose_name='Отправитель-преподаватель',
    )
    text = models.TextField(
        verbose_name='Текст сообщения',
    )
    is_read = models.BooleanField(
        default=False,
        verbose_name='Прочитано',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата отправки',
    )

    class Meta:
        verbose_name = 'Сообщение чата'
        verbose_name_plural = 'Сообщения чатов'
        ordering = ['created_at']

    def __str__(self):
        sender = self.sender_student.fio if self.sender_student else (self.sender_user.get_full_name() or self.sender_user.get_username())
        return f'{sender}: {self.text[:50]}'

    @property
    def sender_name(self):
        if self.sender_student:
            return self.sender_student.fio
        if self.sender_user:
            return self.sender_user.get_full_name() or self.sender_user.get_username()
        return 'Неизвестный'

    @property
    def is_from_student(self):
        return self.sender_student is not None