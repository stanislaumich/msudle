from django.urls import path
from . import views

app_name = 'testing'

urlpatterns = [
    path('', views.test_list, name='list'),
    path('create/', views.test_create, name='create'),
    path('<int:test_id>/edit/', views.test_edit, name='edit'),
    path('<int:test_id>/delete/', views.test_delete, name='delete'),
]