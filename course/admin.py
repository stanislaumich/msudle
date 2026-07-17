from django.contrib import admin
from .models import Course, CourseUserPermission, CourseGroupPermission, CourseGroupStudent, CourseSection, CourseTopic, LearningUnit, CourseAnnouncement


from django.contrib.auth.models import Group


class CourseUserPermissionInline(admin.TabularInline):
    model = CourseUserPermission
    extra = 0
    autocomplete_fields = ('user',)
    classes = ('collapse',)


class CourseGroupPermissionInline(admin.TabularInline):
    model = CourseGroupPermission
    extra = 0
    classes = ('collapse',)


class CourseSectionInline(admin.TabularInline):
    model = CourseSection
    extra = 0
    fields = ('name', 'order')
    ordering = ('order', 'id')
    classes = ('collapse',)


class CourseGroupStudentInline(admin.TabularInline):
    model = CourseGroupStudent
    extra = 0
    autocomplete_fields = ('group',)


class CourseTopicInline(admin.TabularInline):
    model = CourseTopic
    extra = 0
    fields = ('entity_title', 'content', 'order')
    ordering = ('order', 'id')
    classes = ('collapse',)


@admin.register(CourseSection)
class CourseSectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'course', 'order')
    list_filter = ('course',)
    search_fields = ('name', 'course__short_name')
    inlines = [CourseTopicInline]


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('short_name', 'full_name', 'subject', 'identifier')
    list_filter = ('subject__department__faculty__university', 'subject')
    search_fields = ('short_name', 'full_name', 'identifier')
    inlines = [CourseSectionInline, CourseUserPermissionInline, CourseGroupPermissionInline, CourseGroupStudentInline]

    def save_model(self, request, obj, form, change):
        is_new = not obj.pk
        super().save_model(request, obj, form, change)
        if is_new:
            self._assign_default_permissions(request.user, obj)
            self._assign_default_sections(obj)

    def _assign_default_permissions(self, creator, course):
        """При создании курса: создателю — полный доступ, декану — просмотр, зав. кафедрой — просмотр."""
        # Создатель — полный доступ
        CourseUserPermission.objects.get_or_create(
            course=course,
            user=creator,
            defaults={'permission': 'full_access'},
        )
        # Декан факультета (через subject → department → faculty)
        department = course.subject.department
        faculty = department.faculty
        if faculty.dean:
            CourseUserPermission.objects.get_or_create(
                course=course,
                user=faculty.dean,
                defaults={'permission': 'view'},
            )
        # Заведующий кафедрой
        if department.head:
            CourseUserPermission.objects.get_or_create(
                course=course,
                user=department.head,
                defaults={'permission': 'view'},
            )
        # Группы УМО и Ректорат — просмотр
        for group_name in ('УМО', 'Ректорат'):
            try:
                group = Group.objects.get(name=group_name)
                CourseGroupPermission.objects.get_or_create(
                    course=course,
                    group=group,
                    defaults={'permission': 'view'},
                )
            except Group.DoesNotExist:
                pass

    def _assign_default_sections(self, course):
        """Добавляет разделы по умолчанию к новому курсу."""
        for i, name in enumerate(CourseSection.DEFAULT_SECTIONS, start=1):
            CourseSection.objects.get_or_create(
                course=course,
                name=name,
                defaults={'order': i},
            )


@admin.register(CourseUserPermission)
class CourseUserPermissionAdmin(admin.ModelAdmin):
    list_display = ('course', 'user', 'permission')
    list_filter = ('permission', 'course')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'course__short_name')
    autocomplete_fields = ('user',)


@admin.register(CourseGroupPermission)
class CourseGroupPermissionAdmin(admin.ModelAdmin):
    list_display = ('course', 'group', 'permission')
    list_filter = ('permission', 'course')
    search_fields = ('group__name', 'course__short_name')


class LearningUnitInline(admin.TabularInline):
    model = LearningUnit
    extra = 0
    fields = ('title', 'content_type', 'file', 'link', 'order')
    ordering = ('order', 'id')
    classes = ('collapse',)


@admin.register(CourseTopic)
class CourseTopicAdmin(admin.ModelAdmin):
    list_display = ('entity_title', 'content', 'section', 'order')
    list_filter = ('section__course', 'section')
    search_fields = ('entity_title', 'content', 'section__name')
    inlines = [LearningUnitInline]


@admin.register(LearningUnit)
class LearningUnitAdmin(admin.ModelAdmin):
    list_display = ('title', 'content_type', 'topic', 'order')
    list_filter = ('content_type', 'topic__section__course')
    search_fields = ('title', 'topic__entity_title', 'topic__content')


@admin.register(CourseGroupStudent)
class CourseGroupStudentAdmin(admin.ModelAdmin):
    list_display = ('course', 'group')
    list_filter = ('course',)
    search_fields = ('course__short_name', 'group__group_number')
    autocomplete_fields = ('group',)


@admin.register(CourseAnnouncement)
class CourseAnnouncementAdmin(admin.ModelAdmin):
    list_display = ('course', 'author', 'text_preview', 'created_at')
    list_filter = ('course',)
    search_fields = ('text', 'course__short_name', 'author__username')

    def text_preview(self, obj):
        return obj.text[:80]
    text_preview.short_description = 'Текст'
