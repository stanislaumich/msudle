from django.urls import path
from . import views, api_views

app_name = 'chat'

urlpatterns = [
    path('', views.chat_list, name='list'),
    path('<int:room_id>/', views.chat_room, name='room'),
    path('start/<int:course_id>/<int:student_id>/', views.chat_start, name='start'),
    path('api/<int:course_id>/<int:student_id>/', api_views.chat_api_messages, name='api_messages'),
]
