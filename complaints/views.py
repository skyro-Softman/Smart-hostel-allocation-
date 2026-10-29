from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

from .models import Complaint
from .forms import ComplaintForm


@login_required
def complaint_list(request):
    complaints = Complaint.objects.filter(user=request.user)
    return render(request, 'complaints/complaint_list.html', {'complaints': complaints})


@login_required
def complaint_create(request):
    if request.method == 'POST':
        form = ComplaintForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.user = request.user
            c.save()
            return redirect('complaint_list')
    else:
        form = ComplaintForm()
    return render(request, 'complaints/complaint_form.html', {'form': form})
