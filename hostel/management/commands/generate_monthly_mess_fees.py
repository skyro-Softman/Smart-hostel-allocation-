from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from accounts.models import Profile
from hostel.models import Fee
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Generate monthly mess fees for all students. Deadline is 15th of the month.'

    def handle(self, *args, **options):
        """Create mess fees for current month if they don't already exist."""
        today = timezone.now().date()
        current_month = today.strftime('%Y-%m')
        
        # Get the 15th of current month as deadline
        deadline = datetime.strptime(f"{current_month}-15", '%Y-%m-%d').date()
        
        # Get all student users
        students = User.objects.filter(profile__role=Profile.ROLE_STUDENT)
        
        created_count = 0
        existing_count = 0
        
        for student in students:
            # Check if mess fee already exists for this month
            existing_fee = Fee.objects.filter(
                user=student,
                fee_type='MESS',
                payment_month=current_month
            ).exists()
            
            if not existing_fee:
                # Create new mess fee
                Fee.objects.create(
                    user=student,
                    fee_type='MESS',
                    amount=4950,  # Monthly mess fee: ₹4950
                    payment_status='DUE',
                    deadline=deadline,
                    payment_month=current_month
                )
                created_count += 1
            else:
                existing_count += 1
        
        message = f"Monthly mess fees processed:\n"
        message += f"- Created: {created_count} new fees\n"
        message += f"- Already exists: {existing_count} fees"
        
        self.stdout.write(self.style.SUCCESS(message))
