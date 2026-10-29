from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from .models import LeaveRequest
from .forms import LeaveRequestForm


@login_required
def leave_list(request):
    leaves = LeaveRequest.objects.filter(user=request.user)
    return render(request, 'attendance/leave_list.html', {'leaves': leaves})


@login_required
def leave_create(request):
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            l = form.save(commit=False)
            l.user = request.user
            # Keep DB-required date fields filled without showing them in the form.
            if l.outgoing_at:
                l.from_date = l.outgoing_at.date()
            else:
                l.from_date = timezone.localdate()

            if l.incoming_at:
                l.to_date = l.incoming_at.date()
            else:
                l.to_date = l.from_date

            l.save()
            return redirect('leave_list')
    else:
        form = LeaveRequestForm()
    return render(request, 'attendance/leave_form.html', {'form': form})
