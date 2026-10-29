from django.shortcuts import render


# Create your views here.

def home(request):
    return render(request, 'students/home.html')


def about(request):
    return render(request, 'students/about.html')


def contact(request):
    return render(request, 'students/contact.html')
