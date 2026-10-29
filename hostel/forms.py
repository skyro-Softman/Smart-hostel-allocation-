import re

from django import forms
from django.contrib.auth import get_user_model

from accounts.models import Profile
from .models import Hostel, Floor, Room, Bed, HostelFeePayment

User = get_user_model()


class HostelForm(forms.ModelForm):
    class Meta:
        model = Hostel
        fields = ('name', 'hostel_type')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'hostel_type': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if len(name) < 3:
            raise forms.ValidationError('Hostel name must be at least 3 characters long.')
        if not re.fullmatch(r"[A-Za-z0-9 .'-]+", name):
            raise forms.ValidationError('Hostel name contains invalid characters.')
        qs = Hostel.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('A hostel with this name already exists.')
        return name


class FloorForm(forms.ModelForm):
    class Meta:
        model = Floor
        fields = ('hostel', 'floor_name', 'is_ground_floor')
        widgets = {
            'hostel': forms.Select(attrs={'class': 'form-select'}),
            'floor_name': forms.TextInput(attrs={'class': 'form-control'}),
            'is_ground_floor': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_floor_name(self):
        floor_name = (self.cleaned_data.get('floor_name') or '').strip()
        if len(floor_name) < 1 or len(floor_name) > 30:
            raise forms.ValidationError('Floor name must be between 1 and 30 characters.')
        if not re.fullmatch(r'[A-Za-z0-9-]+', floor_name):
            raise forms.ValidationError('Floor name can contain only letters, numbers, and hyphen.')
        return floor_name

    def clean(self):
        cleaned_data = super().clean()
        hostel = cleaned_data.get('hostel')
        floor_name = cleaned_data.get('floor_name')
        if hostel and floor_name:
            qs = Floor.objects.filter(hostel=hostel, floor_name__iexact=floor_name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('floor_name', 'This floor already exists in the selected hostel.')
        return cleaned_data


class RoomForm(forms.ModelForm):
    SHARE_CHOICES = [
        (2, '2 Share'),
        (3, '3 Share'),
        (4, '4 Share'),
    ]
    share_count = forms.ChoiceField(
        choices=SHARE_CHOICES, 
        initial=3, 
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Number of beds in this room'
    )

    class Meta:
        model = Room
        fields = ('hostel', 'floor', 'room_number')
        widgets = {
            'hostel': forms.Select(attrs={'class': 'form-select'}),
            'floor': forms.Select(attrs={'class': 'form-select'}),
            'room_number': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        hostel = cleaned_data.get('hostel')
        floor = cleaned_data.get('floor')
        room_number = (cleaned_data.get('room_number') or '').strip().upper()
        share_count = cleaned_data.get('share_count')

        if hostel and floor and floor.hostel_id != hostel.id:
            raise forms.ValidationError('Selected floor does not belong to selected hostel.')

        if room_number:
            if not re.fullmatch(r'[A-Z0-9-]{2,20}', room_number):
                self.add_error('room_number', 'Room number must be 2-20 chars with letters, numbers, and hyphen.')
            else:
                qs = Room.objects.filter(hostel=hostel, room_number__iexact=room_number) if hostel else Room.objects.none()
                if self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
                if qs.exists():
                    self.add_error('room_number', 'This room number already exists in the selected hostel.')
            cleaned_data['room_number'] = room_number

        if share_count and int(share_count) not in (2, 3, 4):
            self.add_error('share_count', 'Share count must be 2, 3, or 4.')
        return cleaned_data

    def save(self, commit=True):
        room = super().save(commit=False)
        share_count = int(self.cleaned_data['share_count'])
        room.capacity = share_count
        if commit:
            room.save()
            bed_labels = ['A', 'B', 'C', 'D'][:share_count]
            for label in bed_labels:
                Bed.objects.get_or_create(room=room, bed_code=label)
        return room


class BedBulkForm(forms.Form):
    room = forms.ModelChoiceField(
        queryset=Room.objects.select_related('hostel', 'floor').all(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    bed_codes = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text='Comma separated bed labels, e.g. A,B,C',
        initial='A,B,C',
    )

    def clean_bed_codes(self):
        value = self.cleaned_data['bed_codes']
        codes = [code.strip().upper() for code in value.split(',') if code.strip()]
        if not codes:
            raise forms.ValidationError('Enter at least one bed code.')
        if len(codes) != len(set(codes)):
            raise forms.ValidationError('Duplicate bed codes are not allowed.')
        for code in codes:
            if not re.fullmatch(r'[A-Z0-9]{1,3}', code):
                raise forms.ValidationError('Each bed code must be 1-3 alphanumeric uppercase characters.')
        return codes

    def save(self):
        room = self.cleaned_data['room']
        codes = self.cleaned_data['bed_codes']
        created = 0
        for code in codes:
            _, was_created = Bed.objects.get_or_create(room=room, bed_code=code)
            if was_created:
                created += 1
        return created


class PaymentUploadForm(forms.ModelForm):
    class Meta:
        model = HostelFeePayment
        fields = ('receipt_file',)
        widgets = {
            'receipt_file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,image/*'})
        }
