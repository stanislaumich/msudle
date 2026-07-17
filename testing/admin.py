from django.contrib import admin
from .models import Test, Question, Choice


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 3


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    show_change_link = True


@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject', 'author', 'created_at', 'updated_at')
    list_filter = ('subject', 'author')
    search_fields = ('name', 'description')
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'test', 'question_type', 'score', 'order')
    list_filter = ('test', 'question_type')
    inlines = [ChoiceInline]
