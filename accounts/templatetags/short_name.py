from django import template
register = template.Library()

@register.filter
def short_name(value):
    """Возвращает 'Фамилия И.О.' для User или 'Иванов И.И.' для Student."""
    if value is None:
        return ''
    if hasattr(value, 'last_name') and hasattr(value, 'first_name'):
        last = value.last_name
        first = value.first_name
        initials = ''.join(p[0].upper() + '.' for p in first.split() if p) if first else ''
        return f'{last} {initials}'.strip() if last else value.get_username()
    if hasattr(value, 'fio'):
        parts = value.fio.strip().split()
        if len(parts) >= 2:
            last = parts[0]
            initials = ''.join(p[0].upper() + '.' for p in parts[1:])
            return f'{last} {initials}'
        return value.fio
    return str(value)