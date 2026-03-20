from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Category
from .serializers import CategorySerializer


@extend_schema_view(
    list=extend_schema(tags=["Catégories"], summary="Liste des catégories"),
    create=extend_schema(tags=["Catégories"], summary="Créer une catégorie"),
    retrieve=extend_schema(tags=["Catégories"], summary="Détail d'une catégorie"),
    update=extend_schema(tags=["Catégories"], summary="Modifier une catégorie"),
    partial_update=extend_schema(tags=["Catégories"], summary="Modifier partiellement une catégorie"),
    destroy=extend_schema(tags=["Catégories"], summary="Supprimer une catégorie"),
)
class CategoryViewSet(viewsets.ModelViewSet):
    """CRUD des catégories. Uniquement les catégories de l'utilisateur connecté."""

    serializer_class = CategorySerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return Category.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
