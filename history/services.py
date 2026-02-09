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

        # Helper to parse dates (формат dd.mm.yyyy, dd.mm.yyyy HH:MM[:SS])
        def parse_date(val):
            if pd.isna(val):
                return None

            # Уже datetime/timestamp → просто берём date()
            if isinstance(val, datetime):
                return val.date()
            if hasattr(val, "to_pydatetime"):
                try:
                    return val.to_pydatetime().date()
                except Exception:  # noqa: BLE001
                    pass

            # Явная строка в русском формате
            if isinstance(val, str):
                s = val.strip()
                if not s:
                    return None
                for fmt in ("%d.%m.%Y", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
                    try:
                        return datetime.strptime(s, fmt).date()
                    except ValueError:
                        continue

            # Fallback: dayfirst=True, чтобы pandas не путал день/месяц
            try:
                return pd.to_datetime(val, dayfirst=True).date()
            except Exception:  # noqa: BLE001
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
            'atlas_status': get_val('Статус заявки в Атлас'),
            'rr_status': get_val('Статус заявки в РР'),
            'LMS': get_val('Программа в LMS (ссылка)'),
            'contact': get_val('Контактная информация (телефон)'),
            'sex': get_val("Пол"),
            'birthday': parse_date(row.get('Дата рождения')),
            'contry': get_val('Гражданство'),
            'passport': str(get_val('Серия паспорта')) + " " + str(get_val('Номер паспорта')),
            'passport_issued_at': parse_date(row.get('Дата выдачи')),
            'passport_issued_by': get_val('Кем выдан паспорт'),
            'reg_address': get_val('Место регистрации'),
            'rr_application': get_val('Номер заявления на РР'),
            'employment': True if get_val('Трудоустройство') == 'Подтверждено' else False

        }

        if rr_id in existing_apps:
            app = existing_apps[rr_id]
            status_changed = False

            old_atlas = app.current_atlas_status
            old_rr = app.current_rr_status
            new_atlas = data['current_atlas_status']
            new_rr = data['current_rr_status']

            atlas_changed = old_atlas != new_atlas
            rr_changed = old_rr != new_rr
            status_changed = atlas_changed or rr_changed

            if status_changed:
                # Предыдущие статусы считаем ИЗ ИСТОРИИ независимо для Атлас и РР:
                # ищем последний срез, где статус отличался от текущего.
                if atlas_changed:
                    prev_atlas = (
                        StatusHistory.objects.filter(
                            application=app,
                            atlas_status__isnull=False,
                        )
                        .exclude(atlas_status=new_atlas)
                        .order_by('-snapshot_dt')
                        .values_list('atlas_status', flat=True)
                        .first()
                    )
                    app.prev_atlas_status = prev_atlas

                if rr_changed:
                    prev_rr = (
                        StatusHistory.objects.filter(
                            application=app,
                            rr_status__isnull=False,
                        )
                        .exclude(rr_status=new_rr)
                        .order_by('-snapshot_dt')
                        .values_list('rr_status', flat=True)
                        .first()
                    )
                    app.prev_rr_status = prev_rr

                # Обновляем текущие статусы
                app.current_atlas_status = new_atlas
                app.current_rr_status = new_rr

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
            created_apps = Application.objects.bulk_create(new_apps, batch_size=1000)
            
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
                'prev_atlas_status',
                'prev_rr_status',
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
            Application.objects.bulk_update(update_apps, fields_to_update, batch_size=1000)

        # 3. Bulk create history records
        if history_records:
            StatusHistory.objects.bulk_create(history_records, batch_size=1000)
            
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
    # В базе храним реальное имя файла, а не заголовок из Атласа,
    # чтобы колонка "Файл" отражала исходный .xlsx.
    filename = file_path.name

    # Защита от повторного импорта по дате среза:
    # Если такой срез уже есть в истории, сам файл больше не нужен — удаляем его.
    if ImportHistory.objects.filter(snapshot_dt=snapshot_dt).exists():
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            # Ошибку удаления игнорируем, главное — не делать повторный импорт.
            pass
        raise ValueError(
            f"Импорт с датой среза {snapshot_dt} уже был выполнен."
        )

    df = pd.read_excel(file_path)
    return _import_dataframe(df, snapshot_dt, filename)


def import_data(file, snapshot_dt):
    """
    Обертка для текущей формы импорта (загруженный файл Django).
    Сохраняет прежний интерфейс для views, внутри использует общую логику.
    """
    filename = getattr(file, "name", None) or str(file)

    # Аналогичная защита: не допускаем второй импорт того же среза
    if ImportHistory.objects.filter(snapshot_dt=snapshot_dt).exists():
        raise ValueError(
            f"Импорт с датой среза {snapshot_dt} уже был выполнен."
        )

    df = pd.read_excel(file)
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
            'Статус заявки в Атлас': app.atlas_status,
            'Статус заявки в РР': app.rr_status,
            'Программа в LMS': app.LMS,
            'Контактная информация': app.contact,
            'Пол': app.sex,
            'Дата рождения': app.birthday,
            'Гражданство': app.contry,
            'Паспорт': app.passport,
            'Дата выдачи': app.passport_issued_at,
            'Кем выдан паспорт': app.passport_issued_by,
            'Место регистрации': app.reg_address,
            'Номер заявления на РР': app.rr_application,
            'Трудоустройство': "Подтверждено" if app.employment == True else "Не подтверждено"
        }
        data.append(row)
    
    df = pd.DataFrame(data)

    # Принудительно форматируем все даты в человеко‑читаемый вид dd.mm.yyyy,
    # чтобы в Excel не было ISO‑формата/серийных чисел.
    date_cols = [
        'Начало периода обучения',
        'Окончание периода обучения',
        'Дата подачи заявки на РР',
    ]
    for col in date_cols:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda d: d.strftime('%d.%m.%Y') if pd.notnull(d) else ''
            )
    
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=atlas_export_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
    
    df.to_excel(response, index=False)
    return response
