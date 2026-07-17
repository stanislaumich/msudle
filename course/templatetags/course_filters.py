from django import template

register = template.Library()


@register.filter(name='get_item')
def get_item(dictionary, key):
    """Возвращает значение из словаря по ключу. Использование: {{ dict|get_item:key }}"""
    return dictionary.get(key)