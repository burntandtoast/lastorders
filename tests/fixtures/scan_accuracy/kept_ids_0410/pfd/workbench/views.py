# excerpt: Sam-Osian/PFD-toolkit django_workbench/workbench/views.py, lines 3276-3278
def save(request, session):
    model_name = request.POST.get("model_name")
    if model_name in {"gpt-4.1-mini", "gpt-4.1"}:
        session["model_name"] = model_name
