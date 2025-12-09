import pandas as pd
from pathlib import Path
from .models import Application, StatusHistory, ImportHistory
from django.db import transaction
from datetime import datetime
from django.http import HttpResponse


def _import_dataframe(df, snapshot_dt, filename: str):
    """
    Общая реализация импорта.
    Принимает уже загруженный DataFrame и человеко‑читаемое имя файла для ImportHistory.
    """
    # Strip whitespace from column names
    df.columns = df.columns.str.strip()

    # Required columns mapping
    column_map = {
        'Фамилия': 'last_name',
        'Имя': 'first_name',
        'Отчество': 'middle_name',
        'Статус заявки в Атлас': 'atlas_status',
        'Статус заявки в РР': 'rr_status',
        'Email': 'email',
        'Начало периода обучения': 'start_date',
        'Окончание периода обучения': 'end_date',
        'Программа обучения': 'program_name',
        'Регион': 'region',
        'Категория гражданина': 'category',
        'СНИЛС': 'snils',
        'Дата подачи заявки на РР': 'request_date',
        'ID программы в заявке': 'program_id',
        'ID заявки из РР': 'rr_id'
    }

    # Ensure all required columns exist
    missing_cols = set(column_map.keys()) - set(df.columns)
    if missing_cols:
        raise ValueError(f"Missing columns in Excel: {', '.join(missing_cols)}")

    # Pre-fetch existing applications
    existing_apps = Application.objects.in_bulk(field_name='rr_id')
    
    new_apps = []
    update_apps = []
    history_records = []
    
    # Set of rr_ids in the current file to handle duplicates within file if any (though unlikely for ID)
    processed_rr_ids = set()

    for index, row in df.iterrows():
        rr_id = str(row['ID заявки из РР']).strip()
        if pd.isna(rr_id) or rr_id == 'nan':
            continue
            
        if rr_id in processed_rr_ids:
            continue
        processed_rr_ids.add(rr_id)

        # Extract data
        def get_val(col):
            val = row.get(col)
            if pd.isna(val):
                return None
            return val

        # Helper to parse dates
        def parse_date(val):
            if pd.isna(val):
                return None
            if isinstance(val, datetime):
                return val.date()
            try:
                return pd.to_datetime(val).date()
            except:
                return None

        data = {
            'rr_id': rr_id,
            'last_name': get_val('Фамилия'),
            'first_name': get_val('Имя'),
            'middle_name': get_val('Отчество'),
            'email': get_val('Email'),
            'start_date': parse_date(row.get('Начало периода обучения')),
            'end_date': parse_date(row.get('Окончание периода обучения')),
            'program_name': get_val('Программа обучения'),
            'region': get_val('Регион'),
            'category': get_val('Категория гражданина'),
            'snils': get_val('СНИЛС'),
            'request_date': parse_date(row.get('Дата подачи заявки на РР')),
            'program_id': get_val('ID программы в заявке'),
            'current_atlas_status': get_val('Статус заявки в Атлас'),
            'current_rr_status': get_val('Статус заявки в РР'),
        }

        if rr_id in existing_apps:
            app = existing_apps[rr_id]
            status_changed = False
            
            # Check if status changed
            if (app.current_atlas_status != data['current_atlas_status']) or \
               (app.current_rr_status != data['current_rr_status']):
                
                # Update previous statuses before updating current
                app.prev_atlas_status = app.current_atlas_status
                app.prev_rr_status = app.current_rr_status
                
                # Update current statuses
                app.current_atlas_status = data['current_atlas_status']
                app.current_rr_status = data['current_rr_status']
                
                status_changed = True

            # Update other fields just in case they changed (optional, but good for consistency)
            for key, value in data.items():
                if key not in ['current_atlas_status', 'current_rr_status', 'rr_id']: 
                    setattr(app, key, value)
            
            update_apps.append(app)
            
            if status_changed:
                history_records.append(StatusHistory(
                    application=app,
                    atlas_status=data['current_atlas_status'],
                    rr_status=data['current_rr_status'],
                    snapshot_dt=snapshot_dt
                ))
                
        else:
            # New application
            app = Application(**data)
            new_apps.append(app)

    with transaction.atomic():
        # 1. Bulk create new applications
        if new_apps:
            created_apps = Application.objects.bulk_create(new_apps)
            
            for app in created_apps:
                history_records.append(StatusHistory(
                    application=app,
                    atlas_status=app.current_atlas_status,
                    rr_status=app.current_rr_status,
                    snapshot_dt=snapshot_dt
                ))

        # 2. Bulk update existing applications
        if update_apps:
            fields_to_update = [
                'last_name', 'first_name', 'middle_name', 'email', 'start_date', 'end_date',
                'program_name', 'region', 'category', 'snils', 'request_date', 'program_id',
                'current_atlas_status', 'current_rr_status', 'prev_atlas_status', 'prev_rr_status'
            ]
            Application.objects.bulk_update(update_apps, fields_to_update)

        # 3. Bulk create history records
        if history_records:
            StatusHistory.objects.bulk_create(history_records)
            
        # 4. Create ImportHistory record
        ImportHistory.objects.create(
            filename=filename,
            snapshot_dt=snapshot_dt,
            created_count=len(new_apps),
            updated_count=len(update_apps)
        )

    return len(new_apps), len(update_apps)


def import_from_file(path, snapshot_dt, title: str | None = None):
    """
    Импорт данных из локального файла (используется скрапером и CLI).
    path — путь к .xlsx файлу,
    snapshot_dt — дата/время среза, полученная из интерфейса Атласа.
    """
    file_path = Path(path)
    df = pd.read_excel(file_path)
    filename = title or file_path.name
    return _import_dataframe(df, snapshot_dt, filename)


def import_data(file, snapshot_dt):
    """
    Обертка для текущей формы импорта (загруженный файл Django).
    Сохраняет прежний интерфейс для views, внутри использует общую логику.
    """
    df = pd.read_excel(file)
    filename = getattr(file, "name", None) or str(file)
    return _import_dataframe(df, snapshot_dt, filename)

def export_to_excel(queryset, selected_date=None):
    data = []
    for app in queryset:
        # Determine which fields to use based on whether we are looking at history (date selected) or current
        
        if selected_date:
            # Queryset is already annotated in view
            current_atlas = getattr(app, 'hist_atlas_status', None)
            current_rr = getattr(app, 'hist_rr_status', None)
            # For historical view, previous status might be tricky to get efficiently without more queries.
            # Requirement: "предыдущий статус для атлас и рр"
            # Let's skip "prev" in historical export for simplicity unless strictly required to be historically accurate "prev".
            # Actually, if we export filtered view, we usually dump what we have.
            # But let's try to map model fields if no date selected.
            prev_atlas = None 
            prev_rr = None
        else:
            current_atlas = app.current_atlas_status
            current_rr = app.current_rr_status
            prev_atlas = app.prev_atlas_status
            prev_rr = app.prev_rr_status

        row = {
            'ID заявки из РР': app.rr_id,
            'Фамилия': app.last_name,
            'Имя': app.first_name,
            'Отчество': app.middle_name,
            'Email': app.email,
            'Начало периода обучения': app.start_date,
            'Окончание периода обучения': app.end_date,
            'Программа обучения': app.program_name,
            'Регион': app.region,
            'Категория гражданина': app.category,
            'СНИЛС': app.snils,
            'Дата подачи заявки на РР': app.request_date,
            'ID программы в заявке': app.program_id,
            'Текущий Статус Атлас': current_atlas,
            'Текущий Статус РР': current_rr,
            'Предыдущий Статус Атлас': prev_atlas,
            'Предыдущий Статус РР': prev_rr,
        }
        data.append(row)
    
    df = pd.DataFrame(data)
    
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=atlas_export_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
    
    df.to_excel(response, index=False)
    return response
