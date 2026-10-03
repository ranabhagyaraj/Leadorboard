from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import Count, Q
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Company, KBEntry, QueryLog
from .permissions import IsAdminUser
from .serializers import KBEntrySerializer, RegisterSerializer


class RegisterView(generics.CreateAPIView):
    queryset = Company.objects.all()
    serializer_class = RegisterSerializer
    authentication_classes = []
    permission_classes = []

    def create(self, request, *args, **kwargs):
        username = request.data.get('username')
        password = request.data.get('password')
        company_name = request.data.get('company_name')
        email = request.data.get('email')

        if not username or not password or not company_name:
            return Response({"error": "username, password, and company_name are required."}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=username).exists():
            return Response({"error": "Username already exists."}, status=status.HTTP_400_BAD_REQUEST)

        # Create User (triggers post_save signal for Company creation & api_key)
        user = User.objects.create_user(username=username, email=email, password=password)
        
        # Update auto-created company profile with company_name
        company = user.company
        company.company_name = company_name
        company.save()

        # Generate JWT access token
        refresh = RefreshToken.for_user(user)

        return Response({
            "username": user.username,
            "company_name": company.company_name,
            "api_key": company.api_key,
            "access": str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        user = authenticate(username=username, password=password)
        if not user:
            return Response({"error": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

        refresh = RefreshToken.for_user(user)
        company = getattr(user, 'company', None)

        return Response({
            "access": str(refresh.access_token),
            "company_name": company.company_name if company else "",
            "api_key": company.api_key if company else "",
        }, status=status.HTTP_200_OK)


class KBQueryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        search_term = request.data.get('search', '').strip()
        if not search_term:
            return Response({"error": "Search field is missing or blank."}, status=status.HTTP_400_BAD_REQUEST)

        company = getattr(request.user, 'company', None)
        if not company:
            return Response({"error": "Company profile not found."}, status=status.HTTP_403_FORBIDDEN)

        # Perform search and write QueryLog atomically
        with transaction.atomic():
            results = KBEntry.objects.filter(
                Q(question__icontains=search_term) | Q(answer__icontains=search_term)
            )
            count = results.count()

            QueryLog.objects.create(
                company=company,
                search_term=search_term,
                results_count=count
            )

        serializer = KBEntrySerializer(results, many=True)
        return Response({
            "search": search_term,
            "count": count,
            "results": serializer.data
        }, status=status.HTTP_200_OK)


from rest_framework.permissions import BasePermission, IsAuthenticated

class IsAdminOrStaff(BasePermission):
    """
    Allows access only to admin or staff users.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser))

class UsageSummaryView(APIView):
    permission_classes = [IsAdminOrStaff]

    def get(self, request):
        total_queries = QueryLog.objects.aggregate(total=Count('id'))['total'] or 0  
        active_companies = QueryLog.objects.values('company').distinct().count()     
        top_search_terms = list(
            QueryLog.objects.values('search_term')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        )

        return Response({
            "total_queries": total_queries,
            "active_companies": active_companies,
            "top_search_terms": top_search_terms
        }, status=status.HTTP_200_OK)

# Create your views here.
