from django.urls import path
from . import views

urlpatterns = [
    path('leaves/', views.leave_list, name='leave_list'),
    path('leaves/new/', views.leave_create, name='leave_create'),
]
