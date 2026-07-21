from django.urls import path
from . import views

app_name = 'students'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.student_list, name='list'),
    path('create/', views.student_create, name='create'),
    path('<int:student_id>/edit/', views.student_edit, name='edit'),
    path('<int:student_id>/delete/', views.student_delete, name='delete'),
    path('<int:student_id>/soft-delete/', views.student_soft_delete, name='soft_delete'),
    path('groups/', views.group_list, name='group_list'),
    path('groups/create/', views.group_create, name='group_create'),
    path('groups/<int:group_id>/edit/', views.group_edit, name='group_edit'),
    path('groups/<int:group_id>/delete/', views.group_delete, name='group_delete'),
    path('archive/', views.archive_list, name='archive'),
    path('archive/<int:deleted_id>/restore/', views.archive_restore, name='archive_restore'),
]