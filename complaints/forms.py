from django import forms
from .models import Complaint


class ComplaintForm(forms.ModelForm):
    class Meta:
        model = Complaint
        fields = ('subject', 'description')
        widgets = {
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Complaint subject'}),
            'description': forms.Textarea(attrs={'rows':4, 'class':'form-control'})
        }

    def clean_subject(self):
        subject = (self.cleaned_data.get('subject') or '').strip()
        if len(subject) < 5:
            raise forms.ValidationError('Subject must be at least 5 characters long.')
        return subject

    def clean_description(self):
        description = (self.cleaned_data.get('description') or '').strip()
        if len(description) < 10:
            raise forms.ValidationError('Description must be at least 10 characters long.')
        return description
