from django.contrib import admin
from django.contrib.auth.models import User, Group
from .models import University, Faculty, Department


DEAN_GROUP = 'Декан'
HEAD_GROUP = 'Заведующий кафедрой'


def _update_group(user, group_name, model, field_name):
    """Добавляет/удаляет пользователя из группы в зависимости от наличия роли."""
    group, _ = Group.objects.get_or_create(name=group_name)
    if user is None:
        return
    has_role = model.objects.filter(**{field_name: user}).exclude(**{field_name: None}).exists()
    if has_role:
        user.groups.add(group)
    else:
        user.groups.remove(group)


@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ('short_name', 'full_name', 'identifier')
    search_fields = ('short_name', 'full_name', 'identifier')


class DepartmentInline(admin.TabularInline):
    model = Department
    extra = 0

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'head':
            kwargs['queryset'] = User.objects.all().order_by('last_name', 'first_name')
            field = super().formfield_for_foreignkey(db_field, request, **kwargs)
            field.label_from_instance = lambda u: f'{u.last_name} {u.first_name} ({u.username})'
            return field
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ('short_name', 'full_name', 'university', 'dean', 'identifier')
    list_filter = ('university',)
    search_fields = ('short_name', 'full_name', 'identifier', 'dean__username', 'dean__last_name', 'dean__first_name')
    inlines = [DepartmentInline]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'dean':
            kwargs['queryset'] = User.objects.all().order_by('last_name', 'first_name')
            field = super().formfield_for_foreignkey(db_field, request, **kwargs)
            field.label_from_instance = lambda u: f'{u.last_name} {u.first_name} ({u.username})'
            return field
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        old_dean = None
        if change:
            old_obj = Faculty.objects.filter(pk=obj.pk).first()
            if old_obj:
                old_dean = old_obj.dean
        super().save_model(request, obj, form, change)
        if old_dean and old_dean != obj.dean:
            _update_group(old_dean, DEAN_GROUP, Faculty, 'dean')
        if obj.dean:
            _update_group(obj.dean, DEAN_GROUP, Faculty, 'dean')

    def save_formset(self, request, form, formset, change):
        """Отслеживает изменения заведующих кафедрами в инлайне."""
        if formset.model == Department:
            # Запоминаем старых заведующих до сохранения
            old_heads = {}
            for inline_form in formset.forms:
                if inline_form.instance and inline_form.instance.pk:
                    old_instance = Department.objects.filter(pk=inline_form.instance.pk).first()
                    if old_instance:
                        old_heads[inline_form.instance.pk] = old_instance.head
            super().save_formset(request, form, formset, change)
            # После сохранения обновляем группы для изменившихся
            for inline_form in formset.forms:
                if inline_form.instance and inline_form.instance.pk:
                    new_head = inline_form.instance.head
                    old_head = old_heads.get(inline_form.instance.pk)
                    if old_head is not None and old_head != new_head:
                        _update_group(old_head, HEAD_GROUP, Department, 'head')
                    if new_head:
                        _update_group(new_head, HEAD_GROUP, Department, 'head')
        else:
            super().save_formset(request, form, formset, change)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('short_name', 'full_name', 'faculty', 'head', 'identifier')
    list_filter = ('faculty__university', 'faculty')
    search_fields = ('short_name', 'full_name', 'identifier', 'head__username', 'head__last_name', 'head__first_name')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'head':
            kwargs['queryset'] = User.objects.all().order_by('last_name', 'first_name')
            field = super().formfield_for_foreignkey(db_field, request, **kwargs)
            field.label_from_instance = lambda u: f'{u.last_name} {u.first_name} ({u.username})'
            return field
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        old_head = None
        if change:
            old_obj = Department.objects.filter(pk=obj.pk).first()
            if old_obj:
                old_head = old_obj.head
        super().save_model(request, obj, form, change)
        if old_head and old_head != obj.head:
            _update_group(old_head, HEAD_GROUP, Department, 'head')
        if obj.head:
            _update_group(obj.head, HEAD_GROUP, Department, 'head')