from django.contrib import admin
from .models import Shifr


@admin.register(Shifr)
class ShifrAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'qualification', 'faculty')
    search_fields = ('code', 'name')
    list_filter = ('faculty',)
