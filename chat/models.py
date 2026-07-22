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