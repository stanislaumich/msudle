from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.http import JsonResponse


admin.site.unregister(User)


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    """UserAdmin с авто-генерацией username из ФИО (через JS) и показом ФИО в автокомплите."""
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff')
    search_fields = ('username', 'first_name', 'last_name', 'email')

    def autocomplete_view(self, request):
        """Кастомный autocomplete — показывает 'Фамилия Имя (username)'."""
        query = request.GET.get('term', '')
        to_field_name = getattr(self, 'to_field_name', 'pk')

        queryset = self.get_search_results(
            request,
            self.model._default_manager.get_queryset(),
            query,
        )[0]

        paginator = Paginator(queryset, 20)
        page = paginator.get_page(1 if not query else None)

        results = []
        for obj in page.object_list:
            text_parts = [obj.last_name, obj.first_name]
            text = ' '.join(filter(None, text_parts)).strip()
            if text:
                text = f'{text} ({obj.username})'
            else:
                text = obj.username
            results.append({
                'id': str(getattr(obj, to_field_name)),
                'text': text,
            })

        return JsonResponse({
            'results': results,
            'pagination': {'more': page.has_next()},
        })

    class Media:
        js = ('admin/js/auto_login.js',)