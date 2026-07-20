from django.urls import path
from . import views

app_name = 'umo'

urlpatterns = [
    path('', views.shifr_list, name='shifr_list'),
    path('create/', views.shifr_create, name='shifr_create'),
    path('<int:pk>/edit/', views.shifr_edit, name='shifr_edit'),
    path('<int:pk>/delete/', views.shifr_delete, name='shifr_delete'),
]