from datetime import date
import re
import uuid

from django.contrib import messages
from django.contrib.auth import login, logout as auth_logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django import forms

from .forms import BootstrapAuthenticationForm, SignUpForm, StudentProfileForm
from .models import Department, Profile


def auto_allocate_student_room(user):
  """Automatically assigns an available hostel room to a newly registered student."""
  from hostel.models import Allocation, Hostel, Room

  profile = getattr(user, 'profile', None)

  # 1. Match hostels by gender criteria case-insensitively with smart single-letter mapping, otherwise get any active hostel
  hostel_qs = Hostel.objects.all()
  if profile and profile.gender:
    raw_gender = str(profile.gender).strip().upper()
    if raw_gender == 'M':
      search_genders = ['MALE', 'M', 'COED', 'ALL']
    elif raw_gender == 'F':
      search_genders = ['FEMALE', 'F', 'COED', 'ALL']
    else:
      search_genders = [raw_gender, 'COED', 'ALL']

    hostel_qs = hostel_qs.filter(hostel_type__in=search_genders)

  hostels = list(hostel_qs)
  if not hostels:
    hostels = list(Hostel.objects.all())

  # 2. Iterate through hostels to find the first room with available capacity
  for hostel in hostels:
    rooms = Room.objects.filter(hostel=hostel).order_by('room_number')
    for room in rooms:
      current_occupancy = Allocation.objects.filter(room=room).count()
      if current_occupancy < room.capacity:
        Allocation.objects.create(user=user, room=room)
        return True
  return False


def get_role_redirect(user):
  """Return a URL where the user with given profile.role should be sent after login/registration."""
  profile = getattr(user, 'profile', None)
  role = getattr(profile, 'role', None)
  if role == Profile.ROLE_ADMIN:
    return reverse('staff_dashboard')
  if role == Profile.ROLE_WARDEN:
    if profile.approved:
      return reverse('warden_dashboard')
    return reverse('approval_required')
  return reverse('student_dashboard')


class RoleBasedLoginView(LoginView):
  template_name = 'registration/login.html'
  authentication_form = BootstrapAuthenticationForm

  def get_success_url(self):
    return get_role_redirect(self.request.user)

  def form_valid(self, form):
    response = super().form_valid(form)
    profile = getattr(self.request.user, 'profile', None)
    if profile and profile.role == Profile.ROLE_WARDEN:
      if profile.approved:
        messages.success(
            self.request,
            'Warden login approved. Welcome to your dashboard.',
        )
      else:
        messages.warning(
            self.request, 'Your warden account is pending admin approval.'
        )
    return response


def logout_user(request):
  auth_logout(request)
  return redirect('login')


def register(request, role):
  role = (role or '').upper()
  if role not in (Profile.ROLE_STUDENT, Profile.ROLE_WARDEN):
    return HttpResponseForbidden('Invalid registration role.')

  if request.method == 'POST':
    form = SignUpForm(request.POST, request.FILES)

    if role == Profile.ROLE_STUDENT:
      form.fields['register_number'].required = True
      form.fields['full_name'].required = True
      form.fields['department'].required = True
      form.fields['address'].required = True
      form.fields['phone_number'].required = True
      form.fields['id_proof'].required = True
      form.fields['distance_from_campus'].required = True
      form.fields['warden_id'].widget = forms.HiddenInput()
    else:  # WARDEN
      form.fields['warden_id'].required = True
      form.fields['full_name'].required = True
      form.fields['phone_number'].required = True
      form.fields['address'].required = True
      form.fields['id_proof'].required = True
      form.fields['register_number'].widget = forms.HiddenInput()
      form.fields['department'].widget = forms.HiddenInput()
      form.fields['year_of_study'].widget = forms.HiddenInput()
      form.fields['distance_from_campus'].widget = forms.HiddenInput()
      form.fields['has_medical_condition'].widget = forms.HiddenInput()
      form.fields['medical_condition_type'].widget = forms.HiddenInput()
      form.fields['medical_details'].widget = forms.HiddenInput()

    if form.is_valid():
      with transaction.atomic():
        user = form.save()
        profile = getattr(user, 'profile', None)
        if profile:
          profile.role = role
          profile.approved = role == Profile.ROLE_STUDENT
          profile.save(update_fields=['role', 'approved'])

        if role == Profile.ROLE_STUDENT:
          # Auto-allocation removed so student must use the spin wheel
          messages.success(
              request,
              'Registration successful! Please proceed to spin the wheel to allocate your room.',
          )

      login(request, user)
      return redirect(get_role_redirect(user))
    else:
      print('FORM ERRORS:', form.errors)
  else:
    form = SignUpForm()

    if role == Profile.ROLE_STUDENT:
      form.fields['register_number'].required = True
      form.fields['full_name'].required = True
      form.fields['department'].required = True
      form.fields['address'].required = True
      form.fields['phone_number'].required = True
      form.fields['id_proof'].required = True
      form.fields['distance_from_campus'].required = True
      form.fields['warden_id'].widget = forms.HiddenInput()
    else:  # WARDEN
      form.fields['warden_id'].required = True
      form.fields['full_name'].required = True
      form.fields['phone_number'].required = True
      form.fields['address'].required = True
      form.fields['id_proof'].required = True
      form.fields['register_number'].widget = forms.HiddenInput()
      form.fields['department'].widget = forms.HiddenInput()
      form.fields['year_of_study'].widget = forms.HiddenInput()
      form.fields['distance_from_campus'].widget = forms.HiddenInput()
      form.fields['has_medical_condition'].widget = forms.HiddenInput()
      form.fields['medical_condition_type'].widget = forms.HiddenInput()
      form.fields['medical_details'].widget = forms.HiddenInput()

  return render(
      request,
      'registration/register.html',
      {'form': form, 'selected_role': role, 'is_student': (role == Profile.ROLE_STUDENT)},
  )


# --- Admin / staff views for approval ---


@login_required
@user_passes_test(
    lambda u: u.is_staff
    or getattr(getattr(u, 'profile', None), 'role', None) == Profile.ROLE_WARDEN
)
def staff_dashboard(request):
  from attendance.models import Attendance, LeaveRequest
  from complaints.models import Complaint
  from hostel.models import Allocation, Bed, Room

  total_beds = Bed.objects.count()
  occupied_beds = Allocation.objects.values('room').distinct().count()
  vacant_beds = total_beds - occupied_beds
  occupancy_rate = round(
      (occupied_beds / total_beds * 100) if total_beds > 0 else 0, 1
  )

  occupancy_stats = {
      'total_beds': total_beds,
      'occupied_beds': occupied_beds,
      'vacant_beds': vacant_beds,
      'occupancy_rate': occupancy_rate,
  }

  today = date.today()
  total_records = Attendance.objects.filter(date=today).count()
  present_count = Attendance.objects.filter(date=today, status='PRESENT').count()
  absent_count = Attendance.objects.filter(date=today, status='ABSENT').count()
  leave_requests = LeaveRequest.objects.filter(status='PENDING').count()

  attendance_stats = {
      'total_records': total_records,
      'present_count': present_count,
      'absent_count': absent_count,
      'leave_requests': leave_requests,
  }

  total_complaints = Complaint.objects.count()
  pending = Complaint.objects.filter(status='PENDING').count()
  resolved = Complaint.objects.filter(status='RESOLVED').count()
  resolution_rate = round(
      (resolved / total_complaints * 100) if total_complaints > 0 else 0, 1
  )

  complaint_stats = {
      'total_complaints': total_complaints,
      'pending': pending,
      'resolved': resolved,
      'resolution_rate': resolution_rate,
  }

  context = {
      'occupancy_stats': occupancy_stats,
      'attendance_stats': attendance_stats,
      'complaint_stats': complaint_stats,
  }
  return render(request, 'accounts/staff_dashboard.html', context)


@login_required
@user_passes_test(lambda u: u.is_staff)
def approve_warden(request, profile_id):
  profile = get_object_or_404(Profile, pk=profile_id, role=Profile.ROLE_WARDEN)
  profile.approved = True
  profile.save()
  messages.success(request, f"Warden '{profile.user.username}' approved.")
  return redirect('staff_dashboard')


@login_required
def approval_required(request):
  profile = getattr(request.user, 'profile', None)
  if profile and profile.role == Profile.ROLE_WARDEN and profile.approved:
    messages.success(
        request, 'Your account is approved. Redirected to Warden Dashboard.'
    )
    return redirect('warden_dashboard')
  return render(request, 'accounts/approval_required.html')


@login_required
def student_dashboard(request):
  from hostel.models import Allocation

  profile = getattr(request.user, 'profile', None)
  if not profile or profile.role != Profile.ROLE_STUDENT:
    return redirect(get_role_redirect(request.user))

  allocation = (
      Allocation.objects.select_related(
          'room', 'room__hostel', 'room__floor'
      )
      .filter(user=request.user)
      .first()
  )

  return render(
      request,
      'accounts/student_dashboard.html',
      {
          'allocation': allocation,
      },
  )


@login_required
def student_hostel_selection(request):
  from hostel.models import Allocation, Hostel, RoomAllocationRequest

  profile = getattr(request.user, 'profile', None)
  if not profile or profile.role != Profile.ROLE_STUDENT:
    return redirect(get_role_redirect(request.user))

  existing_allocation = (
      Allocation.objects.select_related('room', 'room__hostel')
      .filter(user=request.user)
      .first()
  )
  if existing_allocation:
    return redirect('student_dashboard')

  selected_hostel_id = request.GET.get('hostel') or request.POST.get(
      'hostel_id'
  )
  if selected_hostel_id:
    return redirect('room_list', hostel_id=selected_hostel_id)

  pending_request = (
      RoomAllocationRequest.objects.select_related('room', 'room__hostel')
      .filter(
          user=request.user,
          status='PENDING',
      )
      .first()
  )

  # Try filtering by gender with smart mapping for single letters ('M'/'F') vs full words ('MALE'/'FEMALE')
  hostels = []
  if profile and profile.gender:
    raw_gender = str(profile.gender).strip().upper()
    if raw_gender == 'M':
      search_genders = ['MALE', 'M', 'COED', 'ALL']
    elif raw_gender == 'F':
      search_genders = ['FEMALE', 'F', 'COED', 'ALL']
    else:
      search_genders = [raw_gender, 'COED', 'ALL']

    hostels = list(Hostel.objects.filter(
        hostel_type__in=search_genders
    ).order_by('name'))

  # Absolute safety fallback: if gender filter returns nothing, grab ALL hostels in the database
  if not hostels:
    hostels = list(Hostel.objects.all().order_by('name'))

  return render(
      request,
      'accounts/student_hostel_selection.html',
      {
          'hostels': hostels,
          'pending_request': pending_request,
          'student_department': profile.department or '-',
      },
  )


@login_required
def student_attendance_status(request):
  from datetime import timedelta
  from attendance.models import Attendance

  profile = getattr(request.user, 'profile', None)
  if not profile or profile.role != Profile.ROLE_STUDENT:
    return redirect(get_role_redirect(request.user))

  today = date.today()
  since = today - timedelta(days=30)
  attendance_qs = (
      Attendance.objects.filter(user=request.user, date__gte=since)
      .order_by('-date')
  )
  present_count = attendance_qs.filter(status='PRESENT').count()
  absent_count = attendance_qs.filter(status='ABSENT').count()
  total_count = attendance_qs.count()
  percentage = round(
      (present_count / total_count * 100) if total_count else 0, 1
  )

  return render(
      request,
      'accounts/student_attendance_status.html',
      {
          'attendance_qs': attendance_qs,
          'present_count': present_count,
          'absent_count': absent_count,
          'total_count': total_count,
          'percentage': percentage,
          'today': today,
      },
  )


@login_required
def warden_dashboard(request):
  profile = getattr(request.user, 'profile', None)
  if not profile or profile.role != Profile.ROLE_WARDEN:
    return redirect(get_role_redirect(request.user))
  if not profile.approved:
    return redirect('approval_required')

  from hostel.models import Allocation, Floor, Room

  assigned_hostel = profile.hostel_assigned
  floor_data = []
  if assigned_hostel:
    floors = Floor.objects.filter(hostel=assigned_hostel).order_by('floor_name')
    for floor in floors:
      room_cards = []
      rooms = (
          Room.objects.filter(hostel=assigned_hostel, floor=floor)
          .order_by('room_number')
      )
      for room in rooms:
        total_beds = room.beds.count()
        occupied_count = Allocation.objects.filter(room=room).count()
        room_cards.append({
            'room': room,
            'total_beds': total_beds,
            'occupied_count': occupied_count,
            'vacant_count': max(total_beds - occupied_count, 0),
        })
      floor_data.append({'floor': floor, 'rooms': room_cards})

  context = {
      'assigned_hostel': assigned_hostel,
      'floor_data': floor_data,
  }
  return render(request, 'accounts/warden_dashboard.html', context)


@login_required
def warden_room_detail(request, room_id):
  from hostel.models import Allocation, Room

  profile = getattr(request.user, 'profile', None)
  if not profile or profile.role != Profile.ROLE_WARDEN:
    return redirect(get_role_redirect(request.user))
  if not profile.approved:
    return redirect('approval_required')
  if not profile.hostel_assigned:
    messages.warning(request, 'No hostel is assigned to your profile yet.')
    return redirect('warden_dashboard')

  room = get_object_or_404(
      Room.objects.select_related('hostel', 'floor'),
      id=room_id,
      hostel=profile.hostel_assigned,
  )
  beds = list(room.beds.order_by('bed_code'))
  allocations = list(
      Allocation.objects.filter(room=room)
      .select_related('user', 'user__profile')
      .order_by('allocated_date', 'id')
  )

  bed_rows = []
  for idx, bed in enumerate(beds):
    allocated_user = allocations[idx].user if idx < len(allocations) else None
    allocated_profile = (
        getattr(allocated_user, 'profile', None) if allocated_user else None
    )
    bed_rows.append({
        'bed': bed,
        'occupied': allocated_user is not None,
        'student_name': (
            (
                allocated_profile.full_name
                if allocated_profile and allocated_profile.full_name
                else allocated_user.username
            )
            if allocated_user
            else '-'
        ),
        'student_id': allocated_user.username if allocated_user else '-',
        'department': (
            allocated_profile.department
            if allocated_profile and allocated_profile.department
            else '-'
        ),
    })

  return render(
      request,
      'accounts/warden_room_detail.html',
      {
          'room': room,
          'bed_rows': bed_rows,
      },
  )


@login_required
def warden_room_approvals(request):
  from hostel.models import Allocation, RoomAllocationRequest

  profile = getattr(request.user, 'profile', None)
  if not profile or profile.role != Profile.ROLE_WARDEN:
    return redirect(get_role_redirect(request.user))
  if not profile.approved:
    return redirect('approval_required')
  if not profile.hostel_assigned:
    messages.warning(request, 'No hostel is assigned to your profile yet.')
    return redirect('warden_dashboard')

  if request.method == 'POST':
    req_id = request.POST.get('request_id')
    action = request.POST.get('action')
    room_request = get_object_or_404(
        RoomAllocationRequest.objects.select_related('room', 'user'),
        id=req_id,
        room__hostel=profile.hostel_assigned,
        status='PENDING',
    )
    if action == 'approve':
      room = room_request.room
      existing_allocations = Allocation.objects.filter(room=room).count()
      if existing_allocations >= room.capacity:
        messages.error(request, f'Room {room.room_number} is already full.')
      elif Allocation.objects.filter(user=room_request.user).exists():
        student_name = (
            room_request.user.profile.full_name or room_request.user.username
        )
        messages.error(request, f'{student_name} already has a room allocation.')
      else:
        Allocation.objects.create(user=room_request.user, room=room)
        room_request.status = 'APPROVED'
        room_request.reviewed_at = timezone.now()
        room_request.save(update_fields=['status', 'reviewed_at'])
        student_name = (
            room_request.user.profile.full_name or room_request.user.username
        )
        messages.success(request, f'Room request approved for {student_name}.')
    elif action == 'reject':
      room_request.status = 'REJECTED'
      room_request.reviewed_at = timezone.now()
      room_request.save(update_fields=['status', 'reviewed_at'])
      student_name = (
          room_request.user.profile.full_name or room_request.user.username
      )
      messages.info(request, f'Room request rejected for {student_name}.')

    return redirect('warden_room_approvals')

  pending_requests = (
      RoomAllocationRequest.objects.select_related(
          'user', 'user__profile', 'room', 'room__floor'
      )
      .filter(
          room__hostel=profile.hostel_assigned,
          status='PENDING',
      )
  )
  history = (
      RoomAllocationRequest.objects.select_related(
          'user', 'user__profile', 'room', 'room__floor'
      )
      .filter(
          room__hostel=profile.hostel_assigned,
      )
      .exclude(status='PENDING')[:20]
  )

  return render(
      request,
      'accounts/warden_room_approvals.html',
      {
          'pending_requests': pending_requests,
          'history': history,
      },
  )


@login_required
def warden_attendance_marking(request):
  from urllib.parse import urlencode
  from attendance.models import Attendance
  from hostel.models import Allocation, Room

  profile = getattr(request.user, 'profile', None)
  if not profile or profile.role != Profile.ROLE_WARDEN:
    return redirect(get_role_redirect(request.user))
  if not profile.approved:
    return redirect('approval_required')
  if not profile.hostel_assigned:
    messages.warning(request, 'No hostel is assigned to your profile yet.')
    return redirect('warden_dashboard')

  today = date.today()
  floor_filter = (request.GET.get('floor') or '').strip()
  room_query = (request.GET.get('room_q') or '').strip()
  student_query = (request.GET.get('student_q') or '').strip()
  department_filter = (request.GET.get('department') or '').strip()
  year_filter = (request.GET.get('year') or '').strip()

  all_rooms = (
      Room.objects.filter(hostel=profile.hostel_assigned)
      .select_related('floor')
      .order_by('floor__floor_name', 'room_number')
  )
  floor_options = (
      all_rooms.exclude(floor__isnull=True)
      .values('floor_id', 'floor__floor_name')
      .distinct()
      .order_by('floor__floor_name')
  )

  rooms = all_rooms
  if floor_filter.isdigit():
    rooms = rooms.filter(floor_id=int(floor_filter))
  if room_query:
    rooms = rooms.filter(room_number__icontains=room_query)

  selected_room_id = request.GET.get('room') or request.POST.get('room_id')
  selected_room = None

  if selected_room_id:
    selected_room = rooms.filter(id=selected_room_id).first()
  elif rooms.exists():
    selected_room = rooms.first()

  students = []
  if selected_room:
    allocations = (
        Allocation.objects.filter(room=selected_room)
        .select_related('user', 'user__profile')
        .order_by('user__username')
    )

    if student_query:
      allocations = allocations.filter(
          Q(user__username__icontains=student_query)
          | Q(user__profile__full_name__icontains=student_query)
          | Q(user__profile__register_number__icontains=student_query)
      )
    if department_filter:
      allocations = allocations.filter(
          user__profile__department=department_filter
      )
    if year_filter.isdigit():
      allocations = allocations.filter(
          user__profile__year_of_study=int(year_filter)
      )

    for allocation in allocations:
      attendance = Attendance.objects.filter(
          user=allocation.user, date=today
      ).first()
      students.append({
          'allocation': allocation,
          'current_status': attendance.status if attendance else 'ABSENT',
      })

  if request.method == 'POST' and selected_room:
    for item in students:
      allocation = item['allocation']
      status = request.POST.get(f'status_{allocation.user_id}', 'ABSENT')
      if status not in ('PRESENT', 'ABSENT'):
        status = 'ABSENT'
      Attendance.objects.update_or_create(
          user=allocation.user,
          date=today,
          defaults={'status': status},
      )
    messages.success(
        request,
        f'Attendance marked for room {selected_room.room_number} ({today}).',
    )
    redirect_filters = {
        'room': selected_room.id,
        'floor': (request.POST.get('floor') or '').strip(),
        'room_q': (request.POST.get('room_q') or '').strip(),
        'student_q': (request.POST.get('student_q') or '').strip(),
        'department': (request.POST.get('department') or '').strip(),
        'year': (request.POST.get('year') or '').strip(),
    }
    clean_filters = {
        k: v for k, v in redirect_filters.items() if v not in ('', None)
    }
    return redirect(
        f"{reverse('warden_attendance_marking')}?{urlencode(clean_filters)}"
    )

  return render(
      request,
      'accounts/warden_attendance_marking.html',
      {
          'rooms': rooms,
          'floor_options': floor_options,
          'selected_room': selected_room,
          'students': students,
          'today': today,
          'selected_floor': floor_filter,
          'room_query': room_query,
          'student_query': student_query,
          'department_filter': department_filter,
          'year_filter': year_filter,
          'department_choices': Department.objects.values_list(
              'id', 'name'
          ).order_by('name'),
          'year_choices': range(1, 9),
      },
  )


@login_required
def warden_leave_approvals(request):
  from attendance.models import LeaveRequest
  from hostel.models import Allocation

  profile = getattr(request.user, 'profile', None)
  if not profile or profile.role != Profile.ROLE_WARDEN:
    return redirect(get_role_redirect(request.user))
  if not profile.approved:
    return redirect('approval_required')
  if not profile.hostel_assigned:
    messages.warning(request, 'No hostel is assigned to your profile yet.')
    return redirect('warden_dashboard')

  managed_student_ids = (
      Allocation.objects.filter(room__hostel=profile.hostel_assigned)
      .values_list('user_id', flat=True)
      .distinct()
  )

  if request.method == 'POST':
    leave_id = request.POST.get('leave_id')
    action = request.POST.get('action')
    leave = get_object_or_404(
        LeaveRequest, id=leave_id, user_id__in=managed_student_ids
    )
    if action == 'approve':
      leave.status = 'APPROVED'
      leave.save(update_fields=['status'])
      student_name = leave.user.profile.full_name or leave.user.username
      messages.success(request, f'Outpass approved for {student_name}.')
    elif action == 'reject':
      leave.status = 'REJECTED'
      leave.save(update_fields=['status'])
      student_name = leave.user.profile.full_name or leave.user.username
      messages.info(request, f'Outpass rejected for {student_name}.')
    return redirect('warden_leave_approvals')

  pending_leaves = (
      LeaveRequest.objects.select_related('user', 'user__profile')
      .filter(
          user_id__in=managed_student_ids,
          status='PENDING',
      )
      .order_by('-requested_at')
  )
  reviewed_leaves = (
      LeaveRequest.objects.select_related('user')
      .filter(
          user_id__in=managed_student_ids,
          status__in=['APPROVED', 'REJECTED'],
      )
      .order_by('-requested_at')[:20]
  )

  return render(
      request,
      'accounts/warden_leave_approvals.html',
      {
          'pending_leaves': pending_leaves,
          'reviewed_leaves': reviewed_leaves,
      },
  )


@login_required
def warden_complaints(request):
  from complaints.models import Complaint
  from hostel.models import Allocation

  profile = getattr(request.user, 'profile', None)
  if not profile or profile.role != Profile.ROLE_WARDEN:
    return redirect(get_role_redirect(request.user))
  if not profile.approved:
    return redirect('approval_required')
  if not profile.hostel_assigned:
    messages.warning(request, 'No hostel is assigned to your profile yet.')
    return redirect('warden_dashboard')

  managed_student_ids = (
      Allocation.objects.filter(room__hostel=profile.hostel_assigned)
      .values_list('user_id', flat=True)
      .distinct()
  )

  if request.method == 'POST':
    complaint_id = request.POST.get('complaint_id')
    status = request.POST.get('status')
    reply = request.POST.get('reply', '').strip()
    complaint = get_object_or_404(
        Complaint, id=complaint_id, user_id__in=managed_student_ids
    )
    if status in ('PENDING', 'IN_PROGRESS', 'RESOLVED'):
      complaint.status = status
    if reply:
      complaint.warden_reply = reply
      complaint.replied_by = request.user
      complaint.replied_at = timezone.now()
    complaint.save()
    messages.success(request, 'Complaint updated successfully.')
    return redirect('warden_complaints')

  pending_complaints = (
      Complaint.objects.select_related('user', 'user__profile')
      .filter(
          user_id__in=managed_student_ids,
          status__in=['PENDING', 'IN_PROGRESS'],
      )
      .order_by('-created_at')
  )
  resolved_complaints = (
      Complaint.objects.select_related('user', 'replied_by')
      .filter(
          user_id__in=managed_student_ids,
          status='RESOLVED',
      )
      .order_by('-created_at')[:30]
  )
  return render(
      request,
      'accounts/warden_complaints.html',
      {
          'pending_complaints': pending_complaints,
          'resolved_complaints': resolved_complaints,
      },
  )

@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_report_occupancy(request):
  from hostel.models import Allocation, Bed, Hostel, Room

  hostels = Hostel.objects.prefetch_related(
      'rooms__beds', 'rooms__allocations'
  ).all()

  report_data = []
  for hostel in hostels:
    rooms = hostel.rooms.all()
    total_rooms = rooms.count()
    total_beds = Bed.objects.filter(room__hostel=hostel).count()
    occupied_beds = (
        Allocation.objects.filter(room__hostel=hostel)
        .values('room')
        .distinct()
        .count()
    )
    vacant_beds = total_beds - occupied_beds
    occupancy_rate = round(
        (occupied_beds / total_beds * 100) if total_beds > 0 else 0, 1
    )

    report_data.append({
        'hostel': hostel,
        'total_rooms': total_rooms,
        'total_beds': total_beds,
        'occupied_beds': occupied_beds,
        'vacant_beds': vacant_beds,
        'occupancy_rate': occupancy_rate,
    })

  return render(
      request, 'accounts/report_occupancy.html', {'report_data': report_data}
  )


@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_report_attendance(request):
  from datetime import timedelta
  from attendance.models import Attendance, LeaveRequest

  today = date.today()
  last_7_days = [today - timedelta(days=i) for i in range(7)]

  attendance_data = []
  for day in last_7_days:
    total = Attendance.objects.filter(date=day).count()
    present = Attendance.objects.filter(date=day, status='PRESENT').count()
    absent = Attendance.objects.filter(date=day, status='ABSENT').count()
    attendance_data.append({
        'date': day,
        'total': total,
        'present': present,
        'absent': absent,
        'percentage': round(
            (present / total * 100) if total > 0 else 0, 1
        ),
    })

  pending_leaves = (
      LeaveRequest.objects.filter(status='PENDING')
      .select_related('user')
      .order_by('-requested_at')
  )
  approved_leaves = (
      LeaveRequest.objects.filter(status='APPROVED')
      .select_related('user')
      .order_by('-requested_at')[:20]
  )

  return render(
      request,
      'accounts/report_attendance.html',
      {
          'attendance_data': attendance_data,
          'pending_leaves': pending_leaves,
          'approved_leaves': approved_leaves,
      },
  )


@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_report_complaints(request):
  from django.db.models import Count
  from complaints.models import Complaint

  status_summary = Complaint.objects.values('status').annotate(
      count=Count('id')
  )

  pending_complaints = (
      Complaint.objects.filter(status='PENDING')
      .select_related('user')
      .order_by('-created_at')[:30]
  )
  resolved_complaints = (
      Complaint.objects.filter(status='RESOLVED')
      .select_related('user')
      .order_by('-created_at')[:30]
  )

  return render(
      request,
      'accounts/report_complaints.html',
      {
          'status_summary': status_summary,
          'pending_complaints': pending_complaints,
          'resolved_complaints': resolved_complaints,
      },
  )


@login_required
def profile_view(request):
  """View for logged-in users to view and update their profile details and picture."""
  profile = getattr(request.user, 'profile', None)
  if not profile:
    messages.error(request, "User profile not found.")
    return redirect('student_dashboard')

  if request.method == 'POST':
    form = StudentProfileForm(request.POST, request.FILES, instance=profile)
    if form.is_valid():
      updated_profile = form.save(commit=False)
      # Enforce locked gender preservation since the field is disabled
      updated_profile.gender = profile.gender
      updated_profile.save()
      messages.success(request, "Your profile has been updated successfully!")
      return redirect('profile')
    else:
      messages.error(request, "Please correct the errors below.")
  else:
    form = StudentProfileForm(instance=profile)

  return render(request, 'accounts/profile.html', {
      'form': form,
      'profile': profile,
  })
