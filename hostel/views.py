import random
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from .models import Hostel, Allocation, Room, Bed, HostelFeePayment
from .forms import PaymentUploadForm
from accounts.models import Profile


def _warden_needs_approval(request):
    if not request.user.is_authenticated:
        return False
    profile = getattr(request.user, 'profile', None)
    return profile and profile.role == Profile.ROLE_WARDEN and not profile.approved


def _get_target_hostel_type(student):
    """Maps student profile gender strictly to database choices ('MALE' or 'FEMALE')."""
    profile = getattr(student, 'profile', None)
    if not profile or not profile.gender:
        return None
    
    gender = str(profile.gender).strip().upper()
    if gender in ['MALE', 'M']:
        return 'MALE'
    elif gender in ['FEMALE', 'F']:
        return 'FEMALE'
    return None


def run_auto_allocation(student):
    """
    Automated Hostel Allocation Engine.
    Enforces:
    1. Gender Segregation (Male -> Male hostel, Female -> Female hostel)
    2. Ground Floor Priority for Physical Disabilities
    3. Bed Locking & Atomic Capacity Tracking
    """
    if Allocation.objects.filter(user=student, is_active=True).exists():
        return False, "Student already has an active room allocation."

    target_type = _get_target_hostel_type(student)
    if not target_type:
        return False, "Student gender profile is not configured correctly."

    profile = getattr(student, 'profile', None)
    requires_ground = profile.requires_ground_floor if profile else False

    with transaction.atomic():
        available_beds = Bed.objects.select_for_update().filter(
            is_occupied=False, 
            room__hostel__hostel_type=target_type
        )

        if requires_ground:
            ground_beds = available_beds.filter(room__floor__is_ground_floor=True)
            if ground_beds.exists():
                available_beds = ground_beds

        selected_bed = available_beds.first()
        if not selected_bed:
            return False, f"No available beds found for your gender category ({target_type})."

        selected_bed.is_occupied = True
        selected_bed.save()

        room = selected_bed.room
        room.current_occupancy += 1
        room.save()

        Allocation.objects.create(
            user=student,
            room=room,
            bed=selected_bed,
            is_active=True
        )

        return True, f"Allocated to {room.hostel.name} - Room {room.room_number}, Bed {selected_bed.bed_code}."


def hostel_list(request):
    if _warden_needs_approval(request):
        return redirect('approval_required')
    
    if request.user.is_authenticated:
        active_allocation = Allocation.objects.filter(user=request.user, is_active=True).first()
        if active_allocation:
            return render(request, 'hostel/allocation_status.html', {'allocation': active_allocation})
        
        # Enforce payment verification before letting them proceed
        try:
            payment = request.user.hostel_payment
            if payment.status != 'VERIFIED':
                return redirect('hostel:upload_receipt')
        except HostelFeePayment.DoesNotExist:
            return redirect('hostel:upload_receipt')
        
        target_type = _get_target_hostel_type(request.user)
        raw_gender = str(request.user.profile.gender).strip() if request.user.profile else ""
        
        # Filter hostels strictly matching the student's gender profile category
        hostels = Hostel.objects.filter(
            hostel_type__in=[target_type, raw_gender.upper()] if target_type else [raw_gender.upper()]
        )

        if not hostels.exists():
            messages.error(request, "No matching gender hostels have been created in the system yet.")
            return render(request, 'hostel/no_hostel.html')

        # Directly redirect unallocated students straight to the spin wheel
        return redirect('hostel:spin_wheel_allocate', hostel_id=hostels.first().pk)

    return redirect('login')


def room_list(request, hostel_id):
    if _warden_needs_approval(request):
        return redirect('approval_required')
    
    target_type = _get_target_hostel_type(request.user)
    raw_gender = str(request.user.profile.gender).strip() if (request.user.is_authenticated and request.user.profile) else ""
    
    hostel = get_object_or_404(
        Hostel, 
        pk=hostel_id, 
        hostel_type__in=[target_type, raw_gender.upper()] if target_type else [raw_gender.upper()]
    )

    student_dept = None
    if request.user.is_authenticated:
        prof = getattr(request.user, 'profile', None)
        if prof:
            student_dept = prof.department

    rooms = hostel.rooms.prefetch_related('beds', 'allocations__user__profile')
    room_data = []
    for room in rooms:
        allocs = list(room.allocations.filter(is_active=True))
        occupied = len(allocs)
        available = room.capacity > occupied
        same_dept_count = 0
        if student_dept:
            for a in allocs:
                d = getattr(getattr(a.user, 'profile', None), 'department', '') or ''
                if d == student_dept:
                    same_dept_count += 1
        is_recommended = available and bool(student_dept) and same_dept_count > 0
        room_data.append({
            'room': room,
            'occupied': occupied,
            'available': available,
            'same_dept_count': same_dept_count,
            'is_recommended': is_recommended,
        })

    return render(request, 'hostel/room_list.html', {
        'hostel': hostel,
        'room_data': room_data,
        'student_dept': student_dept,
    })


@login_required
def spin_wheel_allocate(request, hostel_id):
    if Allocation.objects.filter(user=request.user, is_active=True).exists():
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.method == 'POST':
            return JsonResponse({'status': 'error', 'message': 'You already have an active room allocation.'}, status=400)
        messages.error(request, 'You already have an active room allocation.')
        return redirect('student_dashboard')

    # Enforce payment check gate before spinning
    try:
        payment = request.user.hostel_payment
        if payment.status != 'VERIFIED':
            messages.error(request, 'Your payment receipt must be verified by a warden before you can spin.')
            return redirect('hostel:upload_receipt')
    except HostelFeePayment.DoesNotExist:
        messages.error(request, 'You must upload your hostel fee payment receipt before you can spin.')
        return redirect('hostel:upload_receipt')

    target_type = _get_target_hostel_type(request.user)
    raw_gender = str(request.user.profile.gender).strip() if request.user.profile else ""
    
    hostel = get_object_or_404(
        Hostel, 
        pk=hostel_id, 
        hostel_type__in=[target_type, raw_gender.upper()] if target_type else [raw_gender.upper()]
    )

    if request.method == 'POST':
        with transaction.atomic():
            rooms = hostel.rooms.prefetch_related('beds').select_for_update()
            available_rooms = [r for r in rooms if r.current_occupancy < r.capacity]

            if not available_rooms:
                return JsonResponse({'status': 'error', 'message': 'No available rooms left in this hostel!'}, status=400)

            selected_room = random.choice(available_rooms)
            selected_bed = selected_room.beds.filter(is_occupied=False).first()

            if not selected_bed:
                return JsonResponse({'status': 'error', 'message': 'Selected room has no unassigned bed.'}, status=400)

            selected_bed.is_occupied = True
            selected_bed.save()

            selected_room.current_occupancy += 1
            selected_room.save()

            Allocation.objects.create(
                user=request.user,
                room=selected_room,
                bed=selected_bed,
                is_active=True
            )

        return JsonResponse({
            'status': 'success',
            'room_number': selected_room.room_number,
            'room_id': selected_room.id,
            'message': f'Congratulations! You have been allocated Room {selected_room.room_number}, Bed {selected_bed.bed_code}.'
        })

    return render(request, 'hostel/spin_wheel.html', {
        'hostel': hostel
    })


@login_required
def upload_payment_receipt(request):
    payment, created = HostelFeePayment.objects.get_or_create(student=request.user)
    
    if payment.status == 'VERIFIED':
        messages.info(request, "Your payment has already been verified. Proceeding to spin!")
        target_type = _get_target_hostel_type(request.user)
        raw_gender = str(request.user.profile.gender).strip() if request.user.profile else ""
        hostels = Hostel.objects.filter(hostel_type__in=[target_type, raw_gender.upper()] if target_type else [raw_gender.upper()])
        if hostels.exists():
            return redirect('hostel:spin_wheel_allocate', hostel_id=hostels.first().pk)
        return redirect('student_dashboard')

    if request.method == 'POST':
        form = PaymentUploadForm(request.POST, request.FILES, instance=payment)
        if form.is_valid():
            pay = form.save(commit=False)
            pay.status = 'PENDING'
            pay.save()
            messages.success(request, "Payment receipt uploaded successfully. Waiting for warden verification.")
            return redirect('hostel:upload_receipt')
    else:
        form = PaymentUploadForm(instance=payment)

    return render(request, 'hostel/upload_receipt.html', {
        'form': form,
        'payment': payment
    })


@login_required
def warden_verify_payments(request):
    profile = getattr(request.user, 'profile', None)
    if not profile or profile.role != Profile.ROLE_WARDEN:
        messages.error(request, "Access denied.")
        return redirect('student_dashboard')

    if _warden_needs_approval(request):
        return redirect('approval_required')

    payments = HostelFeePayment.objects.filter(status='PENDING').select_related('student__profile')

    return render(request, 'hostel/warden_verify_payments.html', {
        'payments': payments
    })


@login_required
@require_POST
def process_payment_verification(request, payment_id):
    profile = getattr(request.user, 'profile', None)
    if not profile or profile.role != Profile.ROLE_WARDEN:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    payment = get_object_or_404(HostelFeePayment, pk=payment_id)
    action = request.POST.get('action')

    if action == 'verify':
        payment.status = 'VERIFIED'
        payment.verified_at = timezone.now()
        payment.save()
        messages.success(request, f"Payment for {payment.student.username} has been verified.")
    elif action == 'reject':
        payment.status = 'REJECTED'
        payment.warden_comment = request.POST.get('comment', '')
        payment.save()
        messages.warning(request, f"Payment for {payment.student.username} was rejected.")

    return redirect('hostel:warden_verify_payments')


@login_required
def allocation_slip_view(request):
    # Fetch the active allocation for the logged-in student
    allocation = get_object_or_404(Allocation, user=request.user, is_active=True)
    context = {
        'allocation': allocation,
    }
    return render(request, 'hostel/allocation_slip.html', context)
