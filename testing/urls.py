from django.urls import path
from . import views, api_views

app_name = 'testing'

urlpatterns = [
    path('', views.test_list, name='list'),
    path('create/', views.test_create, name='create'),
    path('<int:test_id>/edit/', views.test_edit, name='edit'),
    path('<int:test_id>/delete/', views.test_delete, name='delete'),
    path('<int:test_id>/preview/', views.test_preview, name='preview'),
    # API для вопросов
    path('api/my-tests/', api_views.api_my_tests, name='api_my_tests'),
    path('api/<int:test_id>/questions/', api_views.api_question_list, name='api_question_list'),
    path('api/<int:test_id>/questions/create/', api_views.api_question_create, name='api_question_create'),
    path('api/question/<int:question_id>/update/', api_views.api_question_update, name='api_question_update'),
]
