from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Subquery, OuterRef, Count
from .forms import ImportForm
from .services import import_data, export_to_excel
from .models import Application, StatusHistory, ImportHistory
from datetime import datetime
import pandas as pd
from itertools import zip_longest


def application_list(request):
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
        return export_to_excel(queryset, selected_date)

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
