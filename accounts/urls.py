from django.urls import path
from . import views

urlpatterns = [
    path('generate-login/', views.generate_login_view, name='generate_login'),
]