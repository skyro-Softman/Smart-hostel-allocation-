from django.urls import path
from . import views
from .views import RoleBasedLoginView

# Removed app_name = 'accounts' to allow flat url names to work with base.html

urlpatterns = [
    path('login/', RoleBasedLoginView.as_view(), name='login'),
    path('logout/', views.logout_user, name='logout'),
    path('register/student/', views.register, {'role': 'STUDENT'}, name='register_student'),
    path('register/warden/', views.register, {'role': 'WARDEN'}, name='register_warden'),
    path('register/', views.register, {'role': 'STUDENT'}, name='register'),
    path('staff/', views.staff_dashboard, name='staff_dashboard'),
    path('dashboard/student/hostel-selection/', views.student_hostel_selection, name='student_hostel_selection'),
    path('dashboard/student/', views.student_dashboard, name='student_dashboard'),
    path('dashboard/student/attendance-status/', views.student_attendance_status, name='student_attendance_status'),
    path('dashboard/warden/', views.warden_dashboard, name='warden_dashboard'),
    path('dashboard/warden/room/<int:room_id>/', views.warden_room_detail, name='warden_room_detail'),
    path('dashboard/warden/room-approvals/', views.warden_room_approvals, name='warden_room_approvals'),
    path('dashboard/warden/attendance/', views.warden_attendance_marking, name='warden_attendance_marking'),
    path('dashboard/warden/leave-approvals/', views.warden_leave_approvals, name='warden_leave_approvals'),
    path('dashboard/warden/complaints/', views.warden_complaints, name='warden_complaints'),
    path('staff/approve/<int:profile_id>/', views.approve_warden, name='approve_warden'),
    path('approval-required/', views.approval_required, name='approval_required'),
    path('reports/occupancy/', views.admin_report_occupancy, name='admin_report_occupancy'),
    path('reports/attendance/', views.admin_report_attendance, name='admin_report_attendance'),
    path('reports/complaints/', views.admin_report_complaints, name='admin_report_complaints'),
    
    # User Profile Management
    path('profile/', views.profile_view, name='profile'),
]
