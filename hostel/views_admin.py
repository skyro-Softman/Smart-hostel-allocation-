from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
import re

from accounts.models import Profile
from .forms import BedBulkForm, FloorForm, HostelForm, RoomForm
from .models import Bed, Floor, Hostel, Room


@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_hostel_add(request):
    """Admin adds hostels with floors, then adds rooms to each hostel."""
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_hostel':
            name = request.POST.get('name', '').strip()
            hostel_type = request.POST.get('hostel_type', '').strip()
            num_floors = request.POST.get('num_floors', '').strip()

            if name and hostel_type and num_floors:
                try:
                    if len(name) < 3 or not re.fullmatch(r"[A-Za-z0-9 .'-]+", name):
                        messages.error(request, 'Invalid hostel name format.')
                        return redirect('admin_hostel_add')
                    if Hostel.objects.filter(name__iexact=name).exists():
                        messages.error(request, 'A hostel with this name already exists.')
                        return redirect('admin_hostel_add')
                    hostel = Hostel.objects.create(name=name, hostel_type=hostel_type)
                    num_floors = int(num_floors)
                    if num_floors < 1 or num_floors > 20:
                        messages.error(request, 'Number of floors must be between 1 and 20.')
                        hostel.delete()
                        return redirect('admin_hostel_add')
                    for i in range(1, num_floors + 1):
                        Floor.objects.create(hostel=hostel, floor_name=str(i))
                    messages.success(request, f'Hostel "{name}" with {num_floors} floors added successfully.')
                except Exception as e:
                    messages.error(request, f'Error adding hostel: {e}')
            else:
                messages.error(request, 'All fields are required.')
            return redirect('admin_hostel_add')

        elif action == 'add_room':
            hostel_id = request.POST.get('hostel_id')
            floor_id = request.POST.get('floor_id')
            room_number = request.POST.get('room_number', '').strip().upper()
            share_count = request.POST.get('share_count')

            if hostel_id and floor_id and room_number and share_count:
                try:
                    hostel = Hostel.objects.get(id=hostel_id)
                    floor = Floor.objects.get(id=floor_id, hostel=hostel)
                    share_count = int(share_count)
                    if not re.fullmatch(r'[A-Z0-9-]{2,20}', room_number):
                        messages.error(request, 'Invalid room number format.')
                        return redirect('admin_hostel_add')
                    if share_count not in (2, 3, 4):
                        messages.error(request, 'Share count must be 2, 3, or 4.')
                        return redirect('admin_hostel_add')
                    if Room.objects.filter(hostel=hostel, room_number__iexact=room_number).exists():
                        messages.error(request, f'Room {room_number} already exists in this hostel.')
                        return redirect('admin_hostel_add')
                    room = Room.objects.create(
                        hostel=hostel,
                        floor=floor,
                        room_number=room_number,
                        capacity=share_count
                    )
                    # Auto-create beds
                    bed_labels = ['A', 'B', 'C', 'D'][:share_count]
                    for label in bed_labels:
                        Bed.objects.create(room=room, bed_code=label)
                    messages.success(request, f'Room {room_number} with {share_count} beds added successfully.')
                except Exception as e:
                    messages.error(request, f'Error adding room: {e}')
            else:
                messages.error(request, 'All fields are required.')
            return redirect('admin_hostel_add')

        elif action == 'delete_hostel':
            hostel_id = request.POST.get('hostel_id')
            try:
                hostel = Hostel.objects.get(id=hostel_id)
                name = hostel.name
                hostel.delete()
                messages.success(request, f'Hostel "{name}" and all its rooms deleted.')
            except Hostel.DoesNotExist:
                messages.error(request, 'Hostel not found.')
            return redirect('admin_hostel_add')

        elif action == 'edit_hostel':
            hostel_id = request.POST.get('hostel_id')
            name = request.POST.get('name', '').strip()
            hostel_type = request.POST.get('hostel_type', '').strip()
            try:
                hostel = Hostel.objects.get(id=hostel_id)
                if name and hostel_type:
                    if len(name) < 3 or not re.fullmatch(r"[A-Za-z0-9 .'-]+", name):
                        messages.error(request, 'Invalid hostel name format.')
                        return redirect('admin_hostel_add')
                    if Hostel.objects.filter(name__iexact=name).exclude(pk=hostel.id).exists():
                        messages.error(request, 'A hostel with this name already exists.')
                        return redirect('admin_hostel_add')
                    hostel.name = name
                    hostel.hostel_type = hostel_type
                    hostel.save()
                    messages.success(request, f'Hostel updated to "{name}".')
                else:
                    messages.error(request, 'Name and type are required.')
            except Hostel.DoesNotExist:
                messages.error(request, 'Hostel not found.')
            return redirect('admin_hostel_add')

        elif action == 'delete_room':
            room_id = request.POST.get('room_id')
            try:
                room = Room.objects.get(id=room_id)
                rnum = room.room_number
                room.delete()
                messages.success(request, f'Room {rnum} deleted.')
            except Room.DoesNotExist:
                messages.error(request, 'Room not found.')
            return redirect('admin_hostel_add')

        elif action == 'edit_room':
            room_id = request.POST.get('room_id')
            room_number = request.POST.get('room_number', '').strip().upper()
            floor_id = request.POST.get('floor_id')
            share_count = request.POST.get('share_count')
            try:
                room = Room.objects.get(id=room_id)
                if room_number and floor_id and share_count:
                    floor = Floor.objects.get(id=floor_id, hostel=room.hostel)
                    new_capacity = int(share_count)
                    if not re.fullmatch(r'[A-Z0-9-]{2,20}', room_number):
                        messages.error(request, 'Invalid room number format.')
                        return redirect('admin_hostel_add')
                    if new_capacity not in (2, 3, 4):
                        messages.error(request, 'Share count must be 2, 3, or 4.')
                        return redirect('admin_hostel_add')
                    if Room.objects.filter(hostel=room.hostel, room_number__iexact=room_number).exclude(pk=room.id).exists():
                        messages.error(request, f'Room {room_number} already exists in this hostel.')
                        return redirect('admin_hostel_add')
                    old_capacity = room.capacity
                    room.room_number = room_number
                    room.floor = floor
                    room.capacity = new_capacity
                    room.save()
                    if new_capacity > old_capacity:
                        existing_codes = set(room.beds.values_list('bed_code', flat=True))
                        for label in ['A', 'B', 'C', 'D'][:new_capacity]:
                            if label not in existing_codes:
                                Bed.objects.create(room=room, bed_code=label)
                    messages.success(request, f'Room {room_number} updated.')
                else:
                    messages.error(request, 'All fields are required.')
            except (Room.DoesNotExist, Floor.DoesNotExist, ValueError) as e:
                messages.error(request, f'Error updating room: {e}')
            return redirect('admin_hostel_add')

    hostels = Hostel.objects.prefetch_related('floors', 'rooms__beds').all()
    return render(request, 'hostel/admin_hostel_add.html', {'hostels': hostels})


@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_warden_list(request):
    """Admin approves wardens and assigns them to hostels."""
    if request.method == 'POST':
        action = request.POST.get('action')
        profile_id = request.POST.get('profile_id')

        if action == 'approve' and profile_id:
            try:
                profile = Profile.objects.get(id=profile_id, role=Profile.ROLE_WARDEN)
                profile.approved = True
                profile.save()
                messages.success(request, f'Warden {profile.user.username} approved.')
            except Exception as e:
                messages.error(request, f'Error approving warden: {e}')
            return redirect('admin_warden_list')

        elif action == 'assign_hostel' and profile_id:
            hostel_id = request.POST.get('hostel_id')
            try:
                profile = Profile.objects.get(id=profile_id, role=Profile.ROLE_WARDEN)
                if hostel_id:
                    hostel = Hostel.objects.get(id=hostel_id)
                    profile.hostel_assigned = hostel
                else:
                    profile.hostel_assigned = None
                profile.save()
                messages.success(request, f'Hostel assignment updated for {profile.user.username}.')
            except Exception as e:
                messages.error(request, f'Error assigning hostel: {e}')
            return redirect('admin_warden_list')

    pending_wardens = Profile.objects.filter(role=Profile.ROLE_WARDEN, approved=False).select_related('user')
    approved_wardens = Profile.objects.filter(role=Profile.ROLE_WARDEN, approved=True).select_related('user', 'hostel_assigned')
    hostels = Hostel.objects.all()

    context = {
        'pending_wardens': pending_wardens,
        'approved_wardens': approved_wardens,
        'hostels': hostels,
    }
    return render(request, 'hostel/admin_warden_list.html', context)


@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_management(request):
    hostel_form = HostelForm(prefix='hostel')
    floor_form = FloorForm(prefix='floor')
    room_form = RoomForm(prefix='room')
    bed_form = BedBulkForm(prefix='bed')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_hostel':
            hostel_form = HostelForm(request.POST, prefix='hostel')
            if hostel_form.is_valid():
                hostel_form.save()
                messages.success(request, 'Hostel added successfully.')
                return redirect('admin_management')
            messages.error(request, 'Could not add hostel. Please check the highlighted fields.')

        elif action == 'add_floor':
            floor_form = FloorForm(request.POST, prefix='floor')
            if floor_form.is_valid():
                floor_form.save()
                messages.success(request, 'Floor added successfully.')
                return redirect('admin_management')
            messages.error(request, 'Could not add floor. Please check the highlighted fields.')

        elif action == 'add_room':
            room_form = RoomForm(request.POST, prefix='room')
            if room_form.is_valid():
                room_form.save()
                messages.success(request, 'Room added successfully.')
                return redirect('admin_management')
            messages.error(request, 'Could not add room. Please check the highlighted fields.')

        elif action == 'add_beds':
            bed_form = BedBulkForm(request.POST, prefix='bed')
            if bed_form.is_valid():
                created = bed_form.save()
                messages.success(request, f'Beds added. Newly created: {created}.')
                return redirect('admin_management')
            messages.error(request, 'Could not add beds. Please check the highlighted fields.')

    hostels = Hostel.objects.prefetch_related('floors', 'rooms').all()
    floors = Floor.objects.select_related('hostel').all()
    rooms = Room.objects.select_related('hostel', 'floor').prefetch_related('beds').all()
    beds = Bed.objects.select_related('room', 'room__hostel').all()

    context = {
        'hostel_form': hostel_form,
        'floor_form': floor_form,
        'room_form': room_form,
        'bed_form': bed_form,
        'hostels': hostels,
        'floors': floors,
        'rooms': rooms,
        'beds': beds,
    }
    return render(request, 'hostel/admin_management.html', context)
