from rest_framework import permissions
from .models import Company

class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user 
            and request.user.is_authenticated 
            and hasattr(request.user, 'company') 
            and request.user.company.role == Company.Role.ADMIN
        )