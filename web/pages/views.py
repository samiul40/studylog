from django.shortcuts import redirect, render


def index(request):
    if request.user.is_authenticated:
        return redirect("learning:dashboard")
    return render(request, "pages/index.html")
