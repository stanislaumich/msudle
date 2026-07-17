from django.contrib import admin
from .models import Subject


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('short_name', 'full_name', 'department', 'identifier')
    list_filter = ('department__faculty__university', 'department__faculty', 'department')
    search_fields = ('short_name', 'full_name', 'identifier')
