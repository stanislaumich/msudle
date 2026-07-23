from django.urls import path
from . import views, api_views

app_name = 'chat'

urlpatterns = [
    path('', views.chat_list, name='list'),
    path('<int:room_id>/', views.chat_room, name='room'),
    path('start/<int:course_id>/<int:student_id>/', views.chat_start, name='start'),
    path('<int:room_id>/delete/', views.chat_soft_delete, name='soft_delete'),
    path('archive/', views.chat_archive, name='archive'),
    path('<int:room_id>/restore/', views.chat_restore, name='restore'),
    path('api/<int:course_id>/<int:student_id>/', api_views.chat_api_messages, name='api_messages'),
    path('group/<int:group_chat_id>/', views.group_chat, name='group_chat'),
    path('group/<int:group_chat_id>/api/', api_views.group_chat_api_messages, name='group_chat_api'),
]
