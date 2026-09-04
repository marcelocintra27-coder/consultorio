from django.utils import timezone


def admin_local_date(request):
    return {"admin_local_date": timezone.localdate().isoformat()}
