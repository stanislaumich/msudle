from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('home/', views.home, name='home'),
    path('student-home/', views.student_home, name='student_home'),
    path('courses/', views.dashboard, name='dashboard'),
]
