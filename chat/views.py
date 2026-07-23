from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.http import HttpResponseBadRequest

from .models import ChatRoom, ChatMessage, GroupChat, GroupChatMessage
from course.models import Course, CourseGroupStudent


@login_required
def chat_list(request):
    """Список чатов пользователя."""
    user = request.user
    is_student = hasattr(user, 'fio')

    if is_student:
        # Студент: комнаты по его курсам (создаются только при первом сообщении)
        enrolled_courses = Course.objects.filter(
            group_students__group_id=user.group_id
        ).distinct()
        rooms = ChatRoom.objects.filter(
            course__in=enrolled_courses,
            student=user,
            is_deleted=False,
        ).select_related('course', 'student').annotate(
            unread=Count('messages', filter=Q(messages__is_read=False, messages__sender_student__isnull=True))
        ).order_by('-created_at')
    else:
        # Преподаватель/админ: комнаты по курсам с правами
        from course.views import _get_user_permission
        # Получаем все курсы, где есть права
        rooms = ChatRoom.objects.filter(is_deleted=False).select_related('course', 'student').annotate(
            unread=Count('messages', filter=Q(messages__is_read=False, messages__sender_student__isnull=False))
        ).order_by('-created_at')

        # Фильтруем по правам (если не админ)
        if not user.is_staff:
            allowed_course_ids = []
            for room in rooms:
                perm = _get_user_permission(user, room.course)
                if perm in ('view', 'edit', 'create_delete', 'full_access'):
                    allowed_course_ids.append(room.course_id)
            rooms = rooms.filter(course_id__in=allowed_course_ids)

    # Групповой чат для студентов
    group_chat = None
    if is_student and user.group_id:
        group_chat, _ = GroupChat.objects.get_or_create(group_id=user.group_id)

    return render(request, 'chat/list.html', {
        'rooms': rooms,
        'is_student': is_student,
        'group_chat': group_chat,
    })


@login_required
def chat_room(request, room_id):
    """Конкретная комната чата."""
    user = request.user
    is_student = hasattr(user, 'fio')

    room = get_object_or_404(ChatRoom.objects.select_related('course', 'student'), id=room_id)

    # Проверка доступа
    if is_student:
        if room.student_id != user.id:
            messages.error(request, 'Нет доступа к этому чату.')
            return redirect('chat:list')
    else:
        from course.views import _get_user_permission
        perm = _get_user_permission(user, room.course)
        allowed = {'view', 'edit', 'create_delete', 'full_access'}
        if perm not in allowed and not user.is_staff:
            messages.error(request, 'Нет доступа к этому чату.')
            return redirect('chat:list')

    messages_list = room.messages.select_related('sender_student', 'sender_user').order_by('created_at')

    # Помечаем сообщения как прочитанные (те, что адресованы текущему пользователю)
    if is_student:
        room.messages.filter(sender_user__isnull=False, is_read=False).update(is_read=True)
    else:
        room.messages.filter(sender_student__isnull=False, is_read=False).update(is_read=True)

    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        if not text:
            messages.error(request, 'Введите текст сообщения.')
            return redirect('chat:room', room_id=room.id)

        if is_student:
            ChatMessage.objects.create(
                room=room,
                sender_student=user,
                text=text,
            )
        else:
            ChatMessage.objects.create(
                room=room,
                sender_user=user,
                text=text,
            )
        return redirect('chat:room', room_id=room.id)

    return render(request, 'chat/room.html', {
        'room': room,
        'messages_list': messages_list,
        'is_student': is_student,
    })


@login_required
def chat_start(request, course_id, student_id):
    """Создать или открыть чат с конкретным студентом по курсу (для преподавателя)."""
    user = request.user
    if hasattr(user, 'fio'):
        messages.error(request, 'Студенты не могут создавать чаты.')
        return redirect('chat:list')

    from course.views import _get_user_permission
    from students.models import Student

    course = get_object_or_404(Course, id=course_id)
    student = get_object_or_404(Student, id=student_id)

    perm = _get_user_permission(user, course)
    allowed = {'edit', 'create_delete', 'full_access'}
    if perm not in allowed and not user.is_staff:
        messages.error(request, 'Нет доступа.')
        return redirect('chat:list')

    room, created = ChatRoom.objects.get_or_create(course=course, student=student, defaults={'is_deleted': False})
    # Если комната была удалена — восстанавливаем
    if not created and room.is_deleted:
        room.is_deleted = False
        room.deleted_at = None
        room.save()
    return redirect('chat:room', room_id=room.id)


@login_required
def chat_soft_delete(request, room_id):
    """Софт-удаление комнаты чата (помечает как удалённую)."""
    user = request.user
    if hasattr(user, 'fio'):
        messages.error(request, 'Только преподаватели могут удалять чаты.')
        return redirect('chat:list')

    room = get_object_or_404(ChatRoom, id=room_id)
    from course.views import _get_user_permission
    perm = _get_user_permission(user, room.course)
    allowed = {'edit', 'create_delete', 'full_access'}
    if perm not in allowed and not user.is_staff:
        messages.error(request, 'Нет доступа.')
        return redirect('chat:list')

    if request.method == 'POST':
        from django.utils import timezone
        room.is_deleted = True
        room.deleted_at = timezone.now()
        room.save()
        messages.success(request, f'Чат с «{room.student.fio}» удалён.')
    return redirect('chat:list')


@login_required
def chat_archive(request):
    """Архив удалённых чатов (для преподавателей)."""
    user = request.user
    if hasattr(user, 'fio'):
        # Студенты тоже могут видеть свои удалённые чаты
        enrolled_courses = Course.objects.filter(
            group_students__group_id=user.group_id
        ).distinct()
        rooms = ChatRoom.objects.filter(
            course__in=enrolled_courses,
            student=user,
            is_deleted=True,
        ).select_related('course', 'student').order_by('-deleted_at')
    else:
        from course.views import _get_user_permission
        rooms = ChatRoom.objects.filter(is_deleted=True).select_related('course', 'student').order_by('-deleted_at')
        if not user.is_staff:
            allowed_course_ids = []
            for room in rooms:
                perm = _get_user_permission(user, room.course)
                if perm in ('view', 'edit', 'create_delete', 'full_access'):
                    allowed_course_ids.append(room.course_id)
            rooms = rooms.filter(course_id__in=allowed_course_ids)

    return render(request, 'chat/archive.html', {
        'rooms': rooms,
        'is_student': hasattr(user, 'fio'),
    })


@login_required
def chat_restore(request, room_id):
    """Восстановление удалённой комнаты чата."""
    user = request.user
    room = get_object_or_404(ChatRoom, id=room_id, is_deleted=True)

    if hasattr(user, 'fio'):
        if room.student_id != user.id:
            messages.error(request, 'Нет доступа.')
            return redirect('chat:archive')
    else:
        from course.views import _get_user_permission
        perm = _get_user_permission(user, room.course)
        allowed = {'edit', 'create_delete', 'full_access'}
        if perm not in allowed and not user.is_staff:
            messages.error(request, 'Нет доступа.')
            return redirect('chat:archive')

    if request.method == 'POST':
        room.is_deleted = False
        room.deleted_at = None
        room.save()
        messages.success(request, f'Чат с «{room.student.fio}» восстановлен.')
    return redirect('chat:list')


@login_required
def group_chat(request, group_chat_id):
    """Групповой чат для студентов группы."""
    user = request.user
    # Только студенты имеют доступ к групповому чату
    if not hasattr(user, 'fio'):
        messages.error(request, 'Групповые чаты доступны только студентам.')
        return redirect('chat:list')

    chat_room = get_object_or_404(
        GroupChat.objects.select_related('group'),
        id=group_chat_id
    )

    # Проверка: студент должен быть в этой группе
    if user.group_id != chat_room.group_id:
        messages.error(request, 'Нет доступа к чату этой группы.')
        return redirect('chat:list')

    messages_list = chat_room.messages.select_related('sender_student').order_by('created_at')

    # Помечаем сообщения от других студентов как прочитанные
    chat_room.messages.filter(is_read=False).exclude(sender_student=user).update(is_read=True)

    return render(request, 'chat/group_chat.html', {
        'chat_room': chat_room,
        'messages_list': messages_list,
        'is_student': True,
    })
