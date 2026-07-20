from django.urls import path
from . import views

app_name = 'structure'

urlpatterns = [
    path('', views.structure_dashboard, name='dashboard'),
    path('university/<int:university_id>/edit/', views.university_edit, name='university_edit'),
    path('faculty/create/', views.faculty_create, name='faculty_create'),
    path('faculty/<int:faculty_id>/edit/', views.faculty_edit, name='faculty_edit'),
    path('faculty/<int:faculty_id>/delete/', views.faculty_delete, name='faculty_delete'),
    path('department/create/', views.department_create, name='department_create'),
    path('department/<int:department_id>/edit/', views.department_edit, name='department_edit'),
    path('department/<int:department_id>/delete/', views.department_delete, name='department_delete'),
]