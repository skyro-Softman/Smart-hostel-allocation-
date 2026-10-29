from django.db import models
from django.conf import settings


class Hostel(models.Model):
    HOSTEL_TYPE_CHOICES = [
        ('MALE', 'Male'),
        ('FEMALE', 'Female'),
    ]

    name = models.CharField(max_length=100)
    hostel_type = models.CharField(max_length=10, choices=HOSTEL_TYPE_CHOICES)

    def __str__(self):
        return f"{self.name} ({self.get_hostel_type_display()})"


class Floor(models.Model):
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='floors')
    floor_name = models.CharField(max_length=30)
    is_ground_floor = models.BooleanField(default=False, help_text="Set to True for Ground Floor rooms")

    class Meta:
        unique_together = ('hostel', 'floor_name')

    def __str__(self):
        return f"{self.hostel.name} - Floor {self.floor_name}"


class Room(models.Model):
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='rooms')
    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name='rooms', null=True, blank=True)
    room_number = models.CharField(max_length=20)
    capacity = models.PositiveIntegerField(default=1)
    current_occupancy = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('hostel', 'room_number')

    @property
    def is_full(self):
        return self.current_occupancy >= self.capacity

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Automatically generate beds (Bed A, Bed B, Bed C...) up to the room's capacity
        if is_new:
            existing_beds_count = self.beds.count()
            beds_to_create = self.capacity - existing_beds_count
            for i in range(beds_to_create):
                bed_letter = chr(65 + i)  # 65 is 'A', 66 is 'B', etc.
                Bed.objects.get_or_create(
                    room=self,
                    bed_code=bed_letter
                )

    def __str__(self):
        if self.floor:
            return f"{self.hostel.name} - Floor {self.floor.floor_name} - {self.room_number}"
        return f"{self.hostel.name} - {self.room_number}"


class Bed(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='beds')
    bed_code = models.CharField(max_length=5, help_text='Single-letter or code, e.g. A, B, C')
    bed_number = models.CharField(max_length=30, editable=False)
    is_occupied = models.BooleanField(default=False)

    class Meta:
        unique_together = ('room', 'bed_code')

    def save(self, *args, **kwargs):
        self.bed_code = (self.bed_code or '').upper().strip()
        self.bed_number = f"{self.room.room_number}-{self.bed_code}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.bed_number


class Allocation(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='allocation')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='allocations')
    bed = models.ForeignKey(Bed, on_delete=models.SET_NULL, null=True, blank=True, related_name='allocations')
    allocated_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} -> {self.room} ({self.bed.bed_code if self.bed else 'No Bed'})"


class RoomAllocationRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='room_requests')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='allocation_requests')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f"Request({self.user.username} -> {self.room.room_number}) - {self.status}"


class HostelFeePayment(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending Verification'),
        ('VERIFIED', 'Verified'),
        ('REJECTED', 'Rejected'),
    ]
    
    student = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='hostel_payment')
    receipt_file = models.FileField(upload_to='payment_receipts/')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    warden_comment = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.student.username} - {self.status}"
