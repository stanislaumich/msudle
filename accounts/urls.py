from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('generate-login/', views.generate_login_view, name='generate_login'),
    path('teacher-groups/', views.teacher_group_list, name='teacher_groups'),
    path('teacher-groups/create/', views.teacher_group_create, name='teacher_group_create'),
    path('teacher-groups/<int:group_id>/edit/', views.teacher_group_edit, name='teacher_group_edit'),
    path('teacher-groups/<int:group_id>/delete/', views.teacher_group_delete, name='teacher_group_delete'),
    path('teachers/', views.teacher_list, name='teacher_list'),
    path('teachers/create/', views.teacher_create, name='teacher_create'),
    path('teachers/<int:user_id>/edit/', views.teacher_edit, name='teacher_edit'),
    path('teachers/<int:user_id>/delete/', views.teacher_delete, name='teacher_delete'),
]
