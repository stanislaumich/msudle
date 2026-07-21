from django import forms
from django.contrib import admin
from .models import Student, StudentGroup, DeletedStudent


class StudentForm(forms.ModelForm):
    """Кастомная форма: поле password — всегда пустой ввод (хэш не показывается)."""
    password = forms.CharField(
        label='Пароль',
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text='Оставьте пустым, чтобы не изменять',
    )

    class Meta:
        model = Student
        fields = '__all__'
        exclude = ('last_login',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['password'].widget.attrs['placeholder'] = '********'


class StudentInline(admin.TabularInline):
    model = Student
    form = StudentForm
    extra = 0
    fields = ('fio', 'login', 'record_book_number', 'password')
    show_change_link = True
    classes = ['collapse']


@admin.register(StudentGroup)
class StudentGroupAdmin(admin.ModelAdmin):
    list_display = ('group_number', 'subgroup_number', 'shifr', 'enrollment_year', 'faculty', 'education_form')
    search_fields = ('group_number', 'shifr__code', 'enrollment_year', 'faculty__full_name', 'education_form')
    autocomplete_fields = ('shifr', 'faculty')
    inlines = [StudentInline]


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    form = StudentForm
    list_display = ('fio', 'login', 'record_book_number', 'get_group_number', 'get_subgroup_number')
    list_filter = ('group__group_number',)
    search_fields = ('fio', 'login', 'group__group_number')

    @admin.display(description='Номер группы')
    def get_group_number(self, obj):
        return obj.group.group_number if obj.group else '-'

    @admin.display(description='Подгруппа')
    def get_subgroup_number(self, obj):
        return obj.group.subgroup_number if obj.group else '-'

    def save_model(self, request, obj, form, change):
        """Хэширует пароль при сохранении, если он был установлен."""
        raw_password = form.cleaned_data.get('password')
        if raw_password:
            obj.set_password(raw_password)
        elif not change:
            obj.set_password('')
        super().save_model(request, obj, form, change)


@admin.register(DeletedStudent)
class DeletedStudentAdmin(admin.ModelAdmin):
    list_display = ('fio', 'login', 'group_name', 'deleted_at')
    search_fields = ('fio', 'login', 'group_name')
    list_filter = ('deleted_at',)
    readonly_fields = ('original_id', 'fio', 'login', 'record_book_number', 'password', 'group_name', 'last_login', 'deleted_at')
