# excerpt: Sam-Osian/PFD-toolkit django_workbench/workbench/services.py, line 75
def get_model(session):
    return (session.get("model_name") or "gpt-4.1-mini").strip() or "gpt-4.1-mini"
