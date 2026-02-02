from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Subquery, OuterRef, Count
from django.conf import settings
from .forms import ImportForm
from .services import import_data, export_to_excel
from .models import Application, StatusHistory, ImportHistory
from datetime import datetime
import pandas as pd
from itertools import zip_longest


def application_list(request):

    if not request.user.is_authenticated:
        messages.warning(request, "Для доступа к странице требуется авторизоваться.")
        return redirect(f'{settings.LOGIN_URL}?next={request.path}')
    
    # Handle file upload
    import_form = ImportForm()
    if request.method == 'POST':
        if 'upload_file' in request.POST: # Distinguish from other posts if any
            import_form = ImportForm(request.POST, request.FILES)
            if import_form.is_valid():
                try:
                    created, updated = import_data(request.FILES['file'], import_form.cleaned_data['snapshot_dt'])
                    messages.success(request, f"Импорт завершен успешно. Создано: {created}, Обновлено: {updated}")
                    return redirect('application_list')
                except Exception as e:
                    messages.error(request, f"Ошибка при импорте: {str(e)}")
    
    # Reset filters explicitly (button "Сброс")
    if request.method == 'GET' and 'reset' in request.GET:
        return redirect('application_list')

    # Fetch import history
    import_history = ImportHistory.objects.all()
    last_import = import_history.first()
    # Unique snapshot points (datetime) for filter dropdown (latest first)
    snapshot_points = (
        ImportHistory.objects
        .order_by('-snapshot_dt')
        .values_list('snapshot_dt', flat=True)
        .distinct()
    )

    queryset = Application.objects.all()
    
    # Filters
    search_query = request.GET.get('search', '')
    program_filter = request.GET.get('program', '')
    
    status_atlas_filter = request.GET.get('status_atlas', '')
    status_rr_filter = request.GET.get('status_rr', '')
    
    prev_status_atlas_filter = request.GET.get('prev_status_atlas', '')
    prev_status_rr_filter = request.GET.get('prev_status_rr', '')
    
    start_date_filter = request.GET.get('start_date', '')
    end_date_filter = request.GET.get('end_date', '')
    
    filter_date = request.GET.get('date', '') # Snapshot date

    if search_query:
        queryset = queryset.filter(
            Q(last_name__icontains=search_query) | 
            Q(first_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(rr_id__icontains=search_query)
        )

    if program_filter:
        queryset = queryset.filter(program_name__icontains=program_filter)

    if start_date_filter:
        queryset = queryset.filter(start_date=start_date_filter)

    if end_date_filter:
        queryset = queryset.filter(end_date=end_date_filter)
        
    # Handling Current vs Historical Status Filters
    selected_dt = None
    if filter_date:
        # сначала пробуем ISO-даты+время из выпадающего списка,
        # если не получилось — пробуем старый формат только с датой
        try:
            selected_dt = datetime.fromisoformat(filter_date)
        except ValueError:
            try:
                selected_dt = datetime.strptime(filter_date, '%Y-%m-%d')
            except ValueError:
                selected_dt = None

    if selected_dt:
        # Subquery: состояние заявки на момент выбранной даты/времени
        latest_history = StatusHistory.objects.filter(
            application=OuterRef('pk'),
            snapshot_dt__lte=selected_dt
        ).order_by('-snapshot_dt')

        queryset = queryset.annotate(
            hist_atlas_status=Subquery(latest_history.values('atlas_status')[:1]),
            hist_rr_status=Subquery(latest_history.values('rr_status')[:1])
        ).filter(hist_atlas_status__isnull=False)  # Только заявки, уже существовавшие к этому моменту

        if status_atlas_filter:
            queryset = queryset.filter(hist_atlas_status=status_atlas_filter)

        if status_rr_filter:
            queryset = queryset.filter(hist_rr_status=status_rr_filter)
    else:
        # Standard filtering
        if status_atlas_filter:
            queryset = queryset.filter(current_atlas_status=status_atlas_filter)
        
        if status_rr_filter:
            queryset = queryset.filter(current_rr_status=status_rr_filter)
            
        if prev_status_atlas_filter:
            queryset = queryset.filter(prev_atlas_status=prev_status_atlas_filter)
            
        if prev_status_rr_filter:
            queryset = queryset.filter(prev_rr_status=prev_status_rr_filter)

    if request.GET.get('export'):
        return export_to_excel(queryset, selected_dt)

    # Statistics (based on filtered queryset)
    stats_atlas = queryset.values('current_atlas_status').annotate(total=Count('id')).order_by('-total')
    stats_rr = queryset.values('current_rr_status').annotate(total=Count('id')).order_by('-total')
    stats_prev_atlas = queryset.values('prev_atlas_status').annotate(total=Count('id')).order_by('-total')
    stats_prev_rr = queryset.values('prev_rr_status').annotate(total=Count('id')).order_by('-total')

    stats_rows = zip_longest(stats_atlas, stats_prev_atlas, stats_rr, stats_prev_rr, fillvalue=None)

    # Get unique values for filter dropdowns
    programs = Application.objects.values_list('program_name', flat=True).distinct().order_by('program_name')
    
    statuses_atlas = Application.objects.values_list('current_atlas_status', flat=True).distinct().order_by('current_atlas_status')
    statuses_rr = Application.objects.values_list('current_rr_status', flat=True).distinct().order_by('current_rr_status')
    
    prev_statuses_atlas = Application.objects.values_list('prev_atlas_status', flat=True).distinct().order_by('prev_atlas_status')
    prev_statuses_rr = Application.objects.values_list('prev_rr_status', flat=True).distinct().order_by('prev_rr_status')

    # Prefetch history
    queryset = queryset.prefetch_related('history')
    
    # Pagination
    paginator = Paginator(queryset, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'programs': programs,
        'statuses_atlas': statuses_atlas,
        'statuses_rr': statuses_rr,
        'prev_statuses_atlas': prev_statuses_atlas,
        'prev_statuses_rr': prev_statuses_rr,
        'selected_date': filter_date,
        'search_query': search_query,
        'program_filter': program_filter,
        'status_atlas_filter': status_atlas_filter,
        'status_rr_filter': status_rr_filter,
        'prev_status_atlas_filter': prev_status_atlas_filter,
        'prev_status_rr_filter': prev_status_rr_filter,
        'start_date_filter': start_date_filter,
        'end_date_filter': end_date_filter,
        'import_form': import_form,
        'stats_atlas': stats_atlas,
        'stats_rr': stats_rr,
        'stats_prev_atlas': stats_prev_atlas,
        'stats_prev_rr': stats_prev_rr,
        'stats_rows': stats_rows,
        'snapshot_points': snapshot_points,
        'import_history': import_history,
        'last_import': last_import,
    }
    return render(request, 'history/list.html', context)

def logout_view(request):
    from django.contrib.auth import logout
    logout(request)
    return redirect('/')

import django_filters
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend


def api_guide(request):
    from django.contrib.auth.models import User
    from rest_framework.authtoken.models import Token
    import requests
    import urllib.parse

    if not request.user.is_authenticated:
        messages.warning(request, 'Для доступа к REST API необходимо войти в систему.')
        return redirect(f'{settings.LOGIN_URL}?next={request.path}')
    
    if not request.user.groups.filter(name="Админ"):
        return redirect('/')

    login = User.objects.filter(username=request.user.username).first()
    tkn = Token.objects.filter(user=login).first()
    
    group = 'application'
    if 'history' in request.GET:
        group = 'history-status'
    url = f'http://{request.get_host()}/api/{group}' 
    headers = { 'Authorization': f'Token {tkn}' }

    params = {}
    for arg in request.POST.dict():
        value = request.POST.dict().get(arg)
        if arg != 'csrfmiddlewaretoken' and arg != 'apiLink' and value != '':
            params.setdefault(arg, value)
    
    if request.method == 'POST':
        response = requests.get(url,headers=headers, params=params)
    else:
        response = requests.get(url,headers=headers)
    import json
    context={
        'login': login,
        'token': tkn,
        'JsonReponse': json.dumps(response.json()[:50]),
        'URL': str(urllib.parse.unquote(response.url))
    }
    if 'history' in request.GET:
        return render(request, "history/history_api_form.html", context=context)
    return render(request, "history/app_api_form.html", context=context)

class ApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Application
        fields =[
            'rr_id',
            'last_name',
            'first_name',
            'middle_name',
            'email',
            'start_date',
            'end_date',
            'program_name',
            'region',
            'category',
            'snils',
            'request_date',
            'program_id',
            'current_atlas_status',
            'current_rr_status',
            'atlas_status',
            'rr_status',
            'LMS',
            'contact',
            'sex',
            'birthday',
            'contry',
            'passport',
            'passport_issued_at',
            'passport_issued_by',
            'reg_address',
            'rr_application',
            'employment'
        ]

class ApplicationFilter(django_filters.FilterSet):
    current_atlas_status = django_filters.CharFilter(field_name='current_atlas_status', lookup_expr='exact')
    current_atlas_status__contains = django_filters.CharFilter(field_name='current_atlas_status', lookup_expr='contains')
    
    program_name = django_filters.CharFilter(field_name='program_name', lookup_expr='exact')
    program_name__contains = django_filters.CharFilter(field_name='program_name', lookup_expr='contains')
    
    start_date = django_filters.CharFilter(field_name='start_date', lookup_expr='exact')
    end_date = django_filters.CharFilter(field_name='end_date', lookup_expr='exact')
    
    region = django_filters.CharFilter(field_name='region', lookup_expr='exact')
    region__contains = django_filters.CharFilter(field_name='region', lookup_expr='contains')

    category = django_filters.CharFilter(field_name='category', lookup_expr='exact')
    category__contains = django_filters.CharFilter(field_name='category', lookup_expr='contains')

    class Meta:
        model = Application
        fields = [] 

class ApplicationViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    filterset_class = ApplicationFilter
    queryset = Application.objects.all()
    serializer_class = ApplicationSerializer
    filter_backends = [DjangoFilterBackend]

class HistorySerializer(serializers.ModelSerializer):
    application = serializers.CharField(source='application.rr_id')
    class Meta:
        model = StatusHistory
        fields =[
            'application',
            'atlas_status',
            'rr_status',
            'snapshot_dt'
        ]

class HistoryFilter(django_filters.FilterSet):
    application_id = django_filters.CharFilter(field_name='application__rr_id', lookup_expr='exact')

    snapshot_dt = django_filters.CharFilter(field_name='snapshot_dt', lookup_expr='contains')

    class Meta:
        model = StatusHistory
        fields = []

class HistoryViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    filterset_class = HistoryFilter
    queryset = StatusHistory.objects.all()
    serializer_class = HistorySerializer
    filter_backends = [DjangoFilterBackend]
