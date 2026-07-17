from django.contrib import admin
from .models import ChatRoom, ChatMessage


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('course', 'student', 'created_at')
    list_filter = ('course',)
    search_fields = ('student__fio', 'course__short_name')


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('room', 'sender_name', 'text_preview', 'is_read', 'created_at')
    list_filter = ('is_read', 'room__course')
    search_fields = ('text', 'sender_student__fio', 'sender_user__username')

    def text_preview(self, obj):
        return obj.text[:80]
    text_preview.short_description = 'Текст'