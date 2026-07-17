from django.contrib import admin
from .models import Test


@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject', 'author', 'created_at', 'updated_at')
    list_filter = ('subject', 'author')
    search_fields = ('name', 'description')