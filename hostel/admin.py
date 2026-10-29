from django.contrib import admin

from .models import Hostel, Floor, Room, Bed, Allocation


@admin.register(Hostel)
class HostelAdmin(admin.ModelAdmin):
    list_display = ('name', 'hostel_type')
    search_fields = ('name',)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('room_number', 'hostel', 'floor', 'capacity', 'current_occupancy')
    list_filter = ('hostel', 'floor')


@admin.register(Floor)
class FloorAdmin(admin.ModelAdmin):
    list_display = ('floor_name', 'hostel')
    list_filter = ('hostel',)


@admin.register(Bed)
class BedAdmin(admin.ModelAdmin):
    list_display = ('bed_number', 'room')
    list_filter = ('room__hostel',)


@admin.register(Allocation)
class AllocationAdmin(admin.ModelAdmin):
    list_display = ('user', 'room', 'allocated_date')
    search_fields = ('user__username', 'room__room_number')
