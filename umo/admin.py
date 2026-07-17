from django.contrib import admin
from .models import Shifr


@admin.register(Shifr)
class ShifrAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'qualification')
    search_fields = ('code', 'name')