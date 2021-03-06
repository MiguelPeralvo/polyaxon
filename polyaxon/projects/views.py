# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import (
    RetrieveUpdateDestroyAPIView,
    CreateAPIView,
    ListAPIView,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from libs.utils import to_bool
from libs.views import ListCreateAPIView
from projects.models import Project, ExperimentGroup
from projects.permissions import (
    IsProjectOwnerOrPublicReadOnly,
    get_permissible_project,
    IsItemProjectOwnerOrPublicReadOnly)
from projects.serializers import (
    ProjectSerializer,
    ExperimentGroupSerializer,
    ExperimentGroupDetailSerializer,
    ProjectDetailSerializer,
)
from projects.tasks import stop_group_experiments


class ProjectCreateView(CreateAPIView):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = (IsAuthenticated,)

    def perform_create(self, serializer):
        project = serializer.validated_data['name']
        user = self.request.user
        if self.queryset.filter(user=user, name=project).count() > 0:
            raise ValidationError('A project with name `{}` already exists.'.format(project))
        serializer.save(user=user)


class ProjectListView(ListAPIView):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = (IsAuthenticated,)

    def filter_queryset(self, queryset):
        username = self.kwargs['username']
        if self.request.user.is_staff or self.request.user.username == username:
            # User checking own projects
            return queryset.filter(user__username=username)
        else:
            # Use checking other user public projects
            return queryset.filter(user__username=username, is_public=True)


class ProjectDetailView(RetrieveUpdateDestroyAPIView):
    queryset = Project.objects.all()
    serializer_class = ProjectDetailSerializer
    permission_classes = (IsAuthenticated, IsProjectOwnerOrPublicReadOnly)
    lookup_field = 'name'

    def filter_queryset(self, queryset):
        username = self.kwargs['username']
        return queryset.filter(user__username=username)


class ExperimentGroupListView(ListCreateAPIView):
    queryset = ExperimentGroup.objects.all()
    serializer_class = ExperimentGroupSerializer
    create_serializer_class = ExperimentGroupDetailSerializer
    permission_classes = (IsAuthenticated,)

    def filter_queryset(self, queryset):
        return queryset.filter(project=get_permissible_project(view=self))

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, project=get_permissible_project(view=self))


class ExperimentGroupDetailView(RetrieveUpdateDestroyAPIView):
    queryset = ExperimentGroup.objects.all()
    serializer_class = ExperimentGroupDetailSerializer
    permission_classes = (IsAuthenticated, IsItemProjectOwnerOrPublicReadOnly)
    lookup_field = 'sequence'

    def filter_queryset(self, queryset):
        return queryset.filter(project=get_permissible_project(view=self))

    def get_object(self):
        obj = super(ExperimentGroupDetailView, self).get_object()
        # Check project permissions
        self.check_object_permissions(self.request, obj)
        return obj


class ExperimentGroupStopView(CreateAPIView):
    queryset = ExperimentGroup.objects.all()
    serializer_class = ExperimentGroupSerializer
    permission_classes = (IsAuthenticated, IsItemProjectOwnerOrPublicReadOnly)
    lookup_field = 'sequence'

    def filter_queryset(self, queryset):
        return queryset.filter(project=get_permissible_project(view=self))

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        pending = request.data.get('pending')
        pending = to_bool(pending) if pending is not None else False
        stop_group_experiments.delay(experiment_group_id=obj.id,
                                     pending=pending,
                                     message='User stopped experiment group')
        return Response(status=status.HTTP_200_OK)
