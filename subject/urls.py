from django.urls import path
from . import views

app_name = 'subject'

urlpatterns = [
    path('', views.subject_list, name='list'),
    path('create/', views.subject_create, name='create'),
    path('<int:subject_id>/edit/', views.subject_edit, name='edit'),
    path('<int:subject_id>/delete/', views.subject_delete, name='delete'),
]