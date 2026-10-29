from django.urls import path
from . import views
from . import views_admin

app_name = 'hostel'

urlpatterns = [
    # Core Hostel & Room Routes
    path('', views.hostel_list, name='hostel_list'),
    path('<int:hostel_id>/rooms/', views.room_list, name='room_list'),
    path('<int:hostel_id>/spin-allocate/', views.spin_wheel_allocate, name='spin_wheel_allocate'),

    # Payment & Verification Workflow Routes
    path('upload-receipt/', views.upload_payment_receipt, name='upload_receipt'),
    path('warden/verify-payments/', views.warden_verify_payments, name='warden_verify_payments'),
    path('warden/verify-payments/<int:payment_id>/process/', views.process_payment_verification, name='process_payment_verification'),

    # Allocation Slip Route
    path('my-allocation-slip/', views.allocation_slip_view, name='allocation_slip'),

    # Admin Management Routes
    path('admin/management/', views_admin.admin_management, name='admin_management'),
    path('admin/hostel-add/', views_admin.admin_hostel_add, name='admin_hostel_add'),
    path('admin/warden-list/', views_admin.admin_warden_list, name='admin_warden_list'),
]
