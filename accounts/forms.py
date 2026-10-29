import re

from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model

from .models import Department, Profile

User = get_user_model()


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)
    full_name = forms.CharField(required=False, max_length=100)
    gender = forms.ChoiceField(
        choices=Profile.GENDER_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Required for proper hostel allocation."
    )
    register_number = forms.CharField(required=False, max_length=20)
    warden_id = forms.CharField(required=False, max_length=20)
    department = forms.ModelChoiceField(
        required=False,
        queryset=Department.objects.none(),
        empty_label='Select Department',
    )
    
    # Updated to a ChoiceField for ND/HND breakdown
    year_of_study = forms.ChoiceField(
        choices=[
            ('', 'Select Year of Study'),
            ('ND 1', 'ND 1'),
            ('ND 2', 'ND 2'),
            ('HND 1', 'HND 1'),
            ('HND 2', 'HND 2'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}))
    phone_number = forms.CharField(required=False, max_length=15)
    photo = forms.ImageField(required=False)
    id_proof = forms.ImageField(required=False)

    # Auto-allocation criteria fields
    distance_from_campus = forms.DecimalField(
        required=False,
        max_digits=6,
        decimal_places=2,
        min_value=0.00,
        widget=forms.NumberInput(attrs={'placeholder': 'Distance in km (e.g., 25.5)'}),
    )
    has_medical_condition = forms.BooleanField(required=False)
    medical_condition_type = forms.ChoiceField(
        choices=Profile.HEALTH_CHOICES,
        required=False,
        initial='NONE',
    )
    medical_details = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Specify medical/disability details if any'}),
    )

    class Meta:
        model = User
        fields = ('email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.all().order_by('name')
        
        # Add Bootstrap classes to widgets for nicer styling
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({'class': 'form-select'})
            else:
                field.widget.attrs.update({'class': 'form-control'})

    def clean_full_name(self):
        full_name = (self.cleaned_data.get('full_name') or '').strip()
        if full_name and len(full_name) < 3:
            raise forms.ValidationError('Full name must be at least 3 characters long.')
        if full_name and not re.fullmatch(r"[A-Za-z .'-]+", full_name):
            raise forms.ValidationError('Full name can contain only letters, spaces, dot, apostrophe, and hyphen.')
        return full_name

    def clean_register_number(self):
        register_number = (self.cleaned_data.get('register_number') or '').strip()
        if register_number:
            if not (4 <= len(register_number) <= 20):
                raise forms.ValidationError('Register number must be 4-20 characters long.')
            if re.search(r'[,.;\'"]', register_number):
                raise forms.ValidationError('Register number cannot contain commas, periods, semicolons, or quotes.')
            if User.objects.filter(username=register_number).exists():
                raise forms.ValidationError('A student with this register number already exists.')
        return register_number

    def clean_warden_id(self):
        warden_id = (self.cleaned_data.get('warden_id') or '').strip().upper()
        if warden_id and not re.fullmatch(r'[A-Z0-9-]{3,20}', warden_id):
            raise forms.ValidationError('Warden ID must be 3-20 chars using letters, numbers, and hyphen.')
        if warden_id and User.objects.filter(username=warden_id).exists():
            raise forms.ValidationError('A warden with this warden ID already exists.')
        return warden_id

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean_phone_number(self):
        phone_number = (self.cleaned_data.get('phone_number') or '').strip()
        if phone_number and not re.fullmatch(r'\d{11}', phone_number):
            raise forms.ValidationError('Phone number must contain exactly 11 digits.')
        return phone_number

    def clean_address(self):
        address = (self.cleaned_data.get('address') or '').strip()
        if address and len(address) < 5:
            raise forms.ValidationError('Address must be at least 5 characters long.')
        return address

    def clean_year_of_study(self):
        year = self.cleaned_data.get('year_of_study')
        valid_years = ['ND 1', 'ND 2', 'HND 1', 'HND 2']
        if year and year not in valid_years:
            raise forms.ValidationError('Please select a valid year of study.')
        return year

    def clean_id_proof(self):
        id_proof = self.cleaned_data.get('id_proof')
        if id_proof and id_proof.size > 5 * 1024 * 1024:
            raise forms.ValidationError('ID proof file size must be less than 5 MB.')
        return id_proof

    def clean(self):
        cleaned_data = super().clean()
        register_number = cleaned_data.get('register_number')
        warden_id = cleaned_data.get('warden_id')
        distance = cleaned_data.get('distance_from_campus')

        if register_number and warden_id:
            raise forms.ValidationError('Provide either Register Number or Warden ID, not both.')

        # Role-based validation logic:
        if register_number:  # Registering as Student
            if distance is None:
                self.add_error('distance_from_campus', 'Distance from campus is required for student hostel allocation.')
        elif warden_id:  # Registering as Warden
            # Clear student-specific metrics so they aren't saved
            cleaned_data['distance_from_campus'] = None
            cleaned_data['has_medical_condition'] = False
            cleaned_data['medical_condition_type'] = 'NONE'
            cleaned_data['medical_details'] = ''

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        register_number = self.cleaned_data.get('register_number') or ''
        warden_id = self.cleaned_data.get('warden_id') or ''
        
        if register_number:
            user.username = register_number
        elif warden_id:
            user.username = warden_id
        else:
            user.username = self.cleaned_data.get('email').split('@')[0]
        
        if commit:
            user.save()
        
        profile = getattr(user, 'profile', None)
        if profile is None:
            profile = Profile.objects.create(user=user)
        
        profile.full_name = self.cleaned_data.get('full_name') or ''
        profile.gender = self.cleaned_data.get('gender')
        profile.register_number = register_number or None
        profile.warden_id = warden_id or None
        profile.department = self.cleaned_data.get('department')
        profile.year_of_study = self.cleaned_data.get('year_of_study') or ''
        profile.address = self.cleaned_data.get('address') or ''
        profile.phone_number = self.cleaned_data.get('phone_number') or ''
        profile.photo = self.cleaned_data.get('photo')
        profile.id_proof = self.cleaned_data.get('id_proof')
        
        # Save allocation criteria (if Student)
        profile.distance_from_campus = self.cleaned_data.get('distance_from_campus') or 0.00
        profile.has_medical_condition = self.cleaned_data.get('has_medical_condition') or False
        profile.medical_condition_type = self.cleaned_data.get('medical_condition_type') or 'NONE'
        profile.medical_details = self.cleaned_data.get('medical_details') or ''
        
        if commit:
            profile.save()
        return user


class StudentProfileForm(forms.ModelForm):
    """Form used by logged-in students to update their profile details and picture. Gender is locked."""
    department = forms.ModelChoiceField(
        required=False,
        queryset=Department.objects.all().order_by('name'),
        empty_label='Select Department',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    class Meta:
        model = Profile
        fields = [
            'photo',
            'full_name',
            'gender',
            'department',
            'year_of_study',
            'phone_number',
            'address',
            'distance_from_campus',
            'has_medical_condition',
            'medical_condition_type',
            'medical_details',
        ]
        widgets = {
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-select', 'disabled': 'disabled'}), # Locked down
            'year_of_study': forms.Select(attrs={'class': 'form-select'}, choices=[
                ('', 'Select Year of Study'),
                ('ND 1', 'ND 1'),
                ('ND 2', 'ND 2'),
                ('HND 1', 'HND 1'),
                ('HND 2', 'HND 2'),
            ]),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'distance_from_campus': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Distance in km'}),
            'has_medical_condition': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'hasMedicalCheck'}),
            'medical_condition_type': forms.Select(attrs={'class': 'form-select'}),
            'medical_details': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Prevent updates to gender through form manipulation by enforcing disabled state value
        if 'gender' in self.fields:
            self.fields['gender'].disabled = True

    def clean_phone_number(self):
        phone_number = (self.cleaned_data.get('phone_number') or '').strip()
        if phone_number and not re.fullmatch(r'\d{11}', phone_number):
            raise forms.ValidationError('Phone number must contain exactly 11 digits.')
        return phone_number


class BootstrapAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})
