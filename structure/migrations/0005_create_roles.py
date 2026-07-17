from django.db import migrations


def create_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name='Декан')
    Group.objects.get_or_create(name='Заведующий кафедрой')


def remove_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=['Декан', 'Заведующий кафедрой']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('structure', '0004_department_head_faculty_dean'),
    ]

    operations = [
        migrations.RunPython(create_roles, remove_roles),
    ]