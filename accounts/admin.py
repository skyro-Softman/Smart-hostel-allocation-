from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'register_number', 'department', 'year_of_study', 'photo')
    search_fields = ('user__username', 'register_number')
