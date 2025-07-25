from rest_framework import viewsets, status
from rest_framework.response import Response
from django.db import transaction
from rest_framework.decorators import action

from ..models.timezone import TimeZone
from ..serializers.timezone import TimeZoneSerializer
from ..sync_mixins.time_zone import TimeZoneSyncMixin
from ..models.device import Device

class TimeZoneViewSet(TimeZoneSyncMixin, viewsets.ModelViewSet):
    queryset = TimeZone.objects.all()
    serializer_class = TimeZoneSerializer
    filterset_fields = ['id', 'name']
    search_fields = ['name']
    ordering_fields = ['id', 'name']

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            # Primeiro cria no banco
            instance = serializer.save()
            
            # Depois replica para todas as catracas ativas
            devices = Device.objects.filter(is_active=True)
            if not devices:
                instance.delete()
                return Response({
                    "error": "Nenhuma catraca ativa encontrada"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            for device in devices:
                self.set_device(device)
                response = self.create_objects("time_zones", [{
                    "id": instance.id,
                    "name": instance.name
                }])
                
                if response.status_code != status.HTTP_201_CREATED:
                    instance.delete()
                    return Response({
                        "error": f"Erro ao criar zona de tempo na catraca {device.name}",
                        "details": response.data
                    }, status=response.status_code)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            # Primeiro atualiza no banco
            instance = serializer.save()
            
            # Depois atualiza em todas as catracas ativas
            devices = Device.objects.filter(is_active=True)
            
            for device in devices:
                self.set_device(device)
                response = self.update_objects(
                    "time_zones",
                    {
                        "id": instance.id,
                        "name": instance.name
                    },
                    {"time_zones": {"id": instance.id}}
                )
                
                if response.status_code != status.HTTP_200_OK:
                    return Response({
                        "error": f"Erro ao atualizar zona de tempo na catraca {device.name}",
                        "details": response.data
                    }, status=response.status_code)

        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        with transaction.atomic():
            # Remove de todas as catracas ativas
            devices = Device.objects.filter(is_active=True)
            
            for device in devices:
                self.set_device(device)
                response = self.destroy_objects(
                    "time_zones",
                    {"time_zones": {"id": instance.id}}
                )
                
                if response.status_code != status.HTTP_204_NO_CONTENT:
                    return Response({
                        "error": f"Erro ao deletar zona de tempo da catraca {device.name}",
                        "details": response.data
                    }, status=response.status_code)

            # Se removeu de todas as catracas, remove do banco
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
