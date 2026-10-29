from django.db import models
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


class Department(models.Model):
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Profile(models.Model):
    ROLE_STUDENT = 'STUDENT'
    ROLE_WARDEN = 'WARDEN'
    ROLE_ADMIN = 'ADMIN'

    ROLE_CHOICES = [
        (ROLE_STUDENT, 'Student'),
        (ROLE_WARDEN, 'Warden'),
        (ROLE_ADMIN, 'Admin'),
    ]

    GENDER_MALE = 'M'
    GENDER_FEMALE = 'F'

    GENDER_CHOICES = [
        (GENDER_MALE, 'Male'),
        (GENDER_FEMALE, 'Female'),
    ]

    HEALTH_CHOICES = [
        ('NONE', 'No Medical Condition'),
        ('PHYSICAL', 'Physical Disability / Mobility Issue'),
        ('ASTHMA', 'Respiratory Condition (e.g., Asthma)'),
        ('OTHER', 'Other Special Need'),
    ]

    YEAR_OF_STUDY_CHOICES = [
        ('ND 1', 'ND 1'),
        ('ND 2', 'ND 2'),
        ('HND 1', 'HND 1'),
        ('HND 2', 'HND 2'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_STUDENT)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True, null=True)
    full_name = models.CharField(max_length=100, blank=True, null=True)
    register_number = models.CharField(max_length=20, blank=True, null=True)
    warden_id = models.CharField(max_length=20, blank=True, null=True, unique=True)
    department = models.ForeignKey(
        Department,
        to_field='name',
        db_column='department',
        on_delete=models.SET_NULL,
        related_name='profiles',
        blank=True,
        null=True,
    )
    year_of_study = models.CharField(
        max_length=10,
        choices=YEAR_OF_STUDY_CHOICES,
        blank=True,
        null=True
    )
    address = models.TextField(blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    id_proof = models.ImageField(upload_to='id_proofs/', blank=True, null=True)
    approved = models.BooleanField(default=False, help_text='Warden approved by admin')
    hostel_assigned = models.ForeignKey(
        'hostel.Hostel', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='wardens', 
        help_text='Hostel assigned to warden'
    )

    # Auto-allocation criteria fields
    distance_from_campus = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        default=0.00, 
        help_text="Distance from home to campus in kilometers"
    )
    has_medical_condition = models.BooleanField(default=False)
    medical_condition_type = models.CharField(
        max_length=20, 
        choices=HEALTH_CHOICES, 
        default='NONE'
    )
    medical_details = models.TextField(blank=True, null=True, help_text="Additional health details if needed")
    requires_ground_floor = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.has_medical_condition and self.medical_condition_type == 'PHYSICAL':
            self.requires_ground_floor = True
        else:
            self.requires_ground_floor = False
        super().save(*args, **kwargs)

    def __str__(self):
        status = 'Approved' if self.approved else 'Pending'
        return f"{self.user.username} - {self.get_role_display()} ({status})"

    def approve(self):
        self.approved = True
        self.save()


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
