from django import forms
from django.utils import timezone
from .models import LeaveRequest


class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ('outgoing_at', 'incoming_at', 'place', 'reason')
        widgets = {
            'outgoing_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'incoming_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'place': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Destination / place of stay'}),
            'reason': forms.Textarea(attrs={'rows':3,'class':'form-control'}),
        }
        labels = {
            'outgoing_at': 'Outgoing Date & Time',
            'incoming_at': 'Incoming Date & Time',
            'place': 'Destination / Place',
            'reason': 'Reason',
        }

    def clean_place(self):
        place = (self.cleaned_data.get('place') or '').strip()
        if len(place) < 3:
            raise forms.ValidationError('Destination/place must be at least 3 characters long.')
        return place

    def clean_reason(self):
        reason = (self.cleaned_data.get('reason') or '').strip()
        if len(reason) < 8:
            raise forms.ValidationError('Reason must be at least 8 characters long.')
        return reason

    def clean(self):
        cleaned_data = super().clean()
        outgoing_at = cleaned_data.get('outgoing_at')
        incoming_at = cleaned_data.get('incoming_at')

        if outgoing_at and incoming_at and incoming_at <= outgoing_at:
            self.add_error('incoming_at', 'Incoming date & time must be after outgoing date & time.')

        if outgoing_at and outgoing_at < timezone.now():
            self.add_error('outgoing_at', 'Outgoing date & time cannot be in the past.')

        return cleaned_data
