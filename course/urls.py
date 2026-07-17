from django.urls import path
from . import views

app_name = 'course'

urlpatterns = [
    path('<int:course_id>/edit/', views.course_edit, name='course_edit'),
    path('section/<int:section_id>/delete/', views.section_delete, name='section_delete'),
    path('section/<int:section_id>/toggle-visibility/', views.section_toggle_visibility, name='section_toggle_visibility'),
    path('topic/<int:topic_id>/delete/', views.topic_delete, name='topic_delete'),
    path('unit/<int:unit_id>/delete/', views.unit_delete, name='unit_delete'),
    path('section/<int:section_id>/add-topic/', views.topic_add, name='topic_add'),
    path('topic/<int:topic_id>/add-unit/', views.unit_add_to_topic, name='unit_add_to_topic'),
    path('section/<int:section_id>/add-unit/', views.unit_add_to_section, name='unit_add_to_section'),
    path('unit/<int:unit_id>/edit/', views.unit_edit, name='unit_edit'),
    path('topic/<int:topic_id>/edit/', views.topic_edit, name='topic_edit'),
    path('section/<int:section_id>/edit/', views.section_edit, name='section_edit'),
    path('topic/<int:topic_id>/toggle-visibility/', views.topic_toggle_visibility, name='topic_toggle_visibility'),
    path('unit/<int:unit_id>/toggle-visibility/', views.unit_toggle_visibility, name='unit_toggle_visibility'),
    path('unit/<int:unit_id>/answer/', views.student_answer, name='student_answer'),
    path('<int:course_id>/view/', views.course_view, name='course_view'),
    path('<int:course_id>/enroll-groups/', views.course_enroll_groups, name='course_enroll_groups'),
    path('groupstudent/<int:gs_id>/unenroll/', views.course_unenroll_group, name='course_unenroll_group'),
    path('<int:course_id>/grades/', views.course_grades, name='course_grades'),
    path('<int:course_id>/student-grades/', views.student_grades, name='student_grades'),
]
