from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.db.models import Q

from .models import ChatRoom, ChatMessage
from course.models import Course, CourseGroupStudent
from course.views import _get_user_permission
from students.models import Student


@login_required
@require_http_methods(["GET", "POST"])
def chat_api_messages(request, course_id, student_id):
    """API для получения и отправки сообщений чата.
    GET  — возвращает JSON с историей сообщений.
    POST — создаёт новое сообщение.
    """
    user = request.user
    is_student = hasattr(user, 'fio')

    course = get_object_or_404(Course, id=course_id)
    target_student = get_object_or_404(Student, id=student_id)

    if is_student:
        # Студент может писать только в свои комнаты
        if target_student.id != user.id:
            return JsonResponse({'error': 'Доступ запрещён'}, status=403)
        # Проверяем, что студент подписан на курс
        if not CourseGroupStudent.objects.filter(course=course, group_id=user.group_id).exists():
            return JsonResponse({'error': 'Вы не подписаны на этот курс'}, status=403)
    else:
        # Проверка прав преподавателя на курс
        perm = _get_user_permission(user, course)
        allowed = {'view', 'edit', 'create_delete', 'full_access'}
        if perm not in allowed and not user.is_staff:
            return JsonResponse({'error': 'Нет доступа к курсу'}, status=403)

    # Получаем или создаём комнату
    room, _ = ChatRoom.objects.get_or_create(course=course, student=target_student)

    if request.method == 'GET':
        messages_qs = room.messages.select_related('sender_student', 'sender_user').order_by('created_at')
        data = []
        for msg in messages_qs:
            data.append({
                'id': msg.id,
                'sender_name': msg.sender_name,
                'is_from_student': msg.is_from_student,
                'text': msg.text,
                'is_read': msg.is_read,
                'created_at': msg.created_at.strftime('%d.%m.%Y %H:%M:%S'),
            })

        # Помечаем сообщения в зависимости от того, кто их читает
        if is_student:
            # Студент читает — помечаем сообщения преподавателя как прочитанные
            room.messages.filter(sender_user__isnull=False, is_read=False).update(is_read=True)
        else:
            # Преподаватель читает — помечаем сообщения студента как прочитанные
            room.messages.filter(sender_student__isnull=False, is_read=False).update(is_read=True)

        return JsonResponse({
            'room_id': room.id,
            'student_name': target_student.fio,
            'student_id': target_student.id,
            'messages': data,
        })

    elif request.method == 'POST':
        import json
        try:
            body = json.loads(request.body.decode('utf-8'))
            text = body.get('text', '').strip()
        except (json.JSONDecodeError, UnicodeDecodeError):
            text = ''

        if not text:
            return JsonResponse({'error': 'Текст сообщения обязателен'}, status=400)

        if is_student:
            msg = ChatMessage.objects.create(
                room=room,
                sender_student=user,
                text=text,
            )
        else:
            msg = ChatMessage.objects.create(
                room=room,
                sender_user=user,
                text=text,
            )

        return JsonResponse({
            'id': msg.id,
            'sender_name': msg.sender_name,
            'is_from_student': is_student,
            'text': msg.text,
            'is_read': msg.is_read,
            'created_at': msg.created_at.strftime('%d.%m.%Y %H:%M:%S'),
        })