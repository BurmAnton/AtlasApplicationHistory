import time
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import yaml
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager


@dataclass
class ExportItem:
    title: str
    snapshot_dt: datetime
    file_path: Path


def load_config(path: str = "scraper_config.yaml") -> Dict[str, Any]:
    """
    Загрузка YAML‑конфига со всеми настройками скрапера.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Файл конфигурации скрапера не найден: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_driver(config: Dict[str, Any]):
    """
    Инициализация WebDriver с настройкой папки загрузки.
    Поддерживаются Chrome и Edge, управление драйвером через webdriver-manager.
    """
    browser_cfg = config.get("browser", {})
    driver_name = (browser_cfg.get("driver") or "chrome").lower()
    download_dir = Path(browser_cfg.get("download_dir") or "downloads").resolve()
    download_dir.mkdir(parents=True, exist_ok=True)

    # Общие настройки headless-режима
    headless = bool(browser_cfg.get("headless", True))

    print(
        f"[scraper] Инициализация драйвера: driver={driver_name}, "
        f"headless={headless}, download_dir={download_dir}"
    )

    if driver_name == "edge":
        options = webdriver.EdgeOptions()
        if headless:
            # Headless-режим (для некоторых сборок стабильнее без суффикса =new)
            options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--remote-debugging-port=0")
        prefs = {
            "download.default_directory": str(download_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        }
        options.add_experimental_option("prefs", prefs)
        service = EdgeService(EdgeChromiumDriverManager().install())
        driver = webdriver.Edge(service=service, options=options)
    else:
        # Chrome/Chromium по умолчанию
        options = webdriver.ChromeOptions()
        if headless:
            # Headless-режим для Chrome 109+ (новый стабильный режим)
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-setuid-sandbox")
        # Раздельный профиль, чтобы избежать конфликтов snap/chromium
        options.add_argument("--user-data-dir=/tmp/chrome-atlas-history")

        # Возможность задать путь до бинаря через config['browser']['binary_path']
        # Если не указан, пытаемся найти браузер в стандартных местах
        binary_path = browser_cfg.get("binary_path")
        common_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/snap/bin/chromium",
        ]
        
        if binary_path:
            binary_path_obj = Path(binary_path)
            if not binary_path_obj.exists():
                # Пытаемся найти Chrome в стандартных местах
                found = False
                for common_path in common_paths:
                    if Path(common_path).exists():
                        binary_path = common_path
                        found = True
                        print(
                            f"[scraper] Указанный путь {browser_cfg.get('binary_path')} не существует. "
                            f"Используется найденный: {binary_path}"
                        )
                        break
                if not found:
                    raise FileNotFoundError(
                        f"Chrome/Chromium не найден по указанному пути: {browser_cfg.get('binary_path')}. "
                        f"Проверьте установку браузера или укажите правильный путь в конфиге."
                    )
        else:
            # Если binary_path не указан, пытаемся найти браузер автоматически
            found = False
            for common_path in common_paths:
                if Path(common_path).exists():
                    binary_path = common_path
                    found = True
                    print(f"[scraper] Автоматически найден браузер: {binary_path}")
                    break
        
        if binary_path:
            options.binary_location = str(binary_path)
            print(f"[scraper] Используется бинарь браузера: {binary_path}")
        prefs = {
            "download.default_directory": str(download_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        }
        options.add_experimental_option("prefs", prefs)

        # Пытаемся найти локальный chromedriver рядом с бинарём Chrome
        # (для Chrome for Testing, который поставляется вместе с chromedriver)
        chromedriver_path = browser_cfg.get("chromedriver_path")
        if not chromedriver_path and binary_path:
            # Ищем chromedriver в той же директории или в соседней папке
            binary_dir = Path(binary_path).parent
            possible_paths = [
                binary_dir / "chromedriver",
                binary_dir.parent / "chromedriver-linux64" / "chromedriver",
            ]
            for p in possible_paths:
                if p.exists():
                    chromedriver_path = str(p)
                    print(f"[scraper] Найден локальный chromedriver: {chromedriver_path}")
                    break
        
        if chromedriver_path:
            service = ChromeService(executable_path=chromedriver_path)
        else:
            # Используем webdriver-manager для автоматического скачивания
            service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

    # Гарантируем минимальную ширину окна (для десктоп‑версии интерфейса)
    min_width = 1500
    width = max(int(browser_cfg.get("window_width", min_width)), min_width)
    height = int(browser_cfg.get("window_height", 800))
    driver.set_window_size(width, height)

    implicit_wait = int(browser_cfg.get("implicit_wait", 5))
    driver.implicitly_wait(implicit_wait)
    return driver, download_dir


def login(driver, config: Dict[str, Any]):
    auth = config.get("auth", {})
    login_url = auth.get("login_url")
    if not login_url:
        raise ValueError("В конфигурации не указан auth.login_url")

    driver.get(login_url)

    wait = WebDriverWait(driver, int(config.get("browser", {}).get("explicit_wait", 20)))

    username_selector = auth.get("username_selector")
    password_selector = auth.get("password_selector")
    submit_selector = auth.get("submit_selector")

    if not (username_selector and password_selector and submit_selector):
        raise ValueError("В конфиге auth.*_selector должны быть заданы username, password и submit.")

    try:
        username_el = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, username_selector))
        )
    except TimeoutException as exc:
        raise RuntimeError(
            f"Не удалось найти поле логина по селектору auth.username_selector={username_selector!r}"
        ) from exc

    try:
        password_el = driver.find_element(By.CSS_SELECTOR, password_selector)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Не удалось найти поле пароля по селектору auth.password_selector={password_selector!r}"
        ) from exc

    try:
        submit_el = driver.find_element(By.CSS_SELECTOR, submit_selector)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Не удалось найти кнопку входа по селектору auth.submit_selector={submit_selector!r}"
        ) from exc

    username_el.clear()
    username_el.send_keys(auth.get("username") or "")
    password_el.clear()
    password_el.send_keys(auth.get("password") or "")
    submit_el.click()

    success_selector = auth.get("success_selector")
    if success_selector:
        try:
            wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, success_selector))
            )
        except TimeoutException as exc:
            raise RuntimeError(
                "Авторизация не подтверждена: не найден элемент "
                f"auth.success_selector={success_selector!r} после входа."
            ) from exc


def open_export_modal(driver, config: Dict[str, Any]):
    pages = config.get("pages", {})
    export_url = pages.get("export_page_url")
    export_link_text = pages.get("export_link_text")
    modal_selector = pages.get("modal_selector")
    toggle_id = pages.get("export_toggle_id")

    if not export_url or not export_link_text or not modal_selector:
        raise ValueError("В конфиге pages должны быть заданы export_page_url, export_link_text и modal_selector.")

    driver.get(export_url)
    wait = WebDriverWait(
        driver, int(config.get("browser", {}).get("explicit_wait", 20))
    )

    # При необходимости сначала раскрываем дропдаун по id
    if toggle_id:
        try:
            toggle_btn = wait.until(EC.element_to_be_clickable((By.ID, toggle_id)))
            toggle_btn.click()
        except TimeoutException as exc:
            raise RuntimeError(
                "Не удалось нажать кнопку открытия меню экспорта "
                f"pages.export_toggle_id={toggle_id!r}."
            ) from exc

    # Поиск ссылки по ПОЛНОМУ тексту, как требуется.
    # Используем normalize-space(.) чтобы учесть пробелы/переносы и возможные дочерние узлы.
    xpath = f"//a[normalize-space(.) = '{export_link_text}']"
    try:
        export_link = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
    except TimeoutException as exc:
        raise RuntimeError(
            "Не удалось найти ссылку/пункт меню для открытия экспорта. "
            f"Искали по полному тексту pages.export_link_text={export_link_text!r}."
        ) from exc

    export_link.click()

    # Ждем появления модального окна
    try:
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, modal_selector)))
    except TimeoutException as exc:
        raise RuntimeError(
            "Не удалось дождаться модального окна экспорта. "
            f"Проверьте pages.modal_selector={modal_selector!r}."
        ) from exc


def load_full_history(driver, config: Dict[str, Any]):
    modal_cfg = config.get("modal", {})
    list_selector = modal_cfg.get("list_container_selector")
    if not list_selector:
        raise ValueError("В конфиге modal.list_container_selector не задан.")

    wait = WebDriverWait(
        driver, int(config.get("browser", {}).get("explicit_wait", 20))
    )
    try:
        container = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, list_selector))
        )
    except TimeoutException as exc:
        raise RuntimeError(
            "Не удалось найти контейнер со списком выгрузок в модальном окне. "
            f"Проверьте modal.list_container_selector={list_selector!r}."
        ) from exc

    max_iter = int(config.get("browser", {}).get("max_scroll_iterations", 30))

    last_height = 0
    for _ in range(max_iter):
        # Текущая высота
        new_height = driver.execute_script("return arguments[0].scrollHeight", container)
        if new_height == last_height:
            # Больше ничего не подгружается
            break
        last_height = new_height
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", container)
        time.sleep(1.0)


def _parse_snapshot_dt(text: str) -> datetime:
    """
    Извлекает из строки дату/время формата 'ДД.MM.ГГГГ, ЧЧ:ММ'.
    Если парсинг не удался — бросает ValueError.
    """
    m = re.search(r"(\d{2}\.\d{2}\.\d{4}).*?(\d{2}:\d{2})", text)
    if not m:
        raise ValueError(f"Не удалось распарсить дату/время из текста: {text!r}")
    date_part, time_part = m.groups()
    return datetime.strptime(f"{date_part} {time_part}", "%d.%m.%Y %H:%M")


def _wait_for_new_file(download_dir: Path, before_files, timeout: int = 60) -> Path:
    """
    Ожидает появления нового .xlsx файла в папке загрузки.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        current_files = set(download_dir.glob("*.xlsx"))
        new_files = current_files - before_files
        # Игнорируем временные файлы
        ready_files = {f for f in new_files if not f.name.endswith(".crdownload") and not f.name.endswith(".part")}
        if ready_files:
            # Возвращаем любой (обычно один)
            return sorted(ready_files, key=lambda p: p.stat().st_mtime)[-1]
        time.sleep(1.0)
    raise TimeoutError("Не удалось дождаться загрузки файла экспорта.")


def collect_and_download_exports(
    driver,
    config: Dict[str, Any],
    download_dir: Path,
    should_download: Optional[Callable[[str, datetime], bool]] = None,
    on_export: Optional[Callable[[ExportItem], None]] = None,
) -> List[ExportItem]:
    modal_cfg = config.get("modal", {})
    list_selector = modal_cfg.get("list_container_selector")
    item_selector = modal_cfg.get("item_selector")
    text_selector = modal_cfg.get("item_text_selector")
    download_selector = modal_cfg.get("download_button_selector")

    if not (list_selector and item_selector and text_selector and download_selector):
        raise ValueError(
            "В конфиге modal должны быть заданы list_container_selector, item_selector, "
            "item_text_selector и download_button_selector."
        )

    # Дожидаемся появления контейнера, но сами элементы выгрузок ищем
    # по всему документу (по требованию) — а не только внутри контейнера.
    wait = WebDriverWait(
        driver, int(config.get("browser", {}).get("explicit_wait", 20))
    )
    try:
        wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, list_selector))
        )
    except TimeoutException as exc:
        raise RuntimeError(
            "Не удалось найти контейнер со списком выгрузок в модальном окне "
            f"при сборе файлов. modal.list_container_selector={list_selector!r}."
        ) from exc

    items: Iterable[Any] = driver.find_elements(By.CSS_SELECTOR, item_selector)

    # Обходим элементы в обратном порядке (от старых к новым),
    # чтобы история импортировалась хронологически.
    items = list(items)[::-1]
    results: List[ExportItem] = []

    # Множество уже существующих файлов, чтобы отследить новые
    existing_files = set(download_dir.glob("*.xlsx"))

    for item in items:
        # Текст, содержащий дату/время. Элемент может «протухать» (stale),
        # поэтому пытаемся перечитать его несколько раз.
        retries = 3
        text = ""
        while retries > 0:
            try:
                text_el = item.find_element(By.CSS_SELECTOR, text_selector)
                text = text_el.text.strip()
                break
            except StaleElementReferenceException:
                retries -= 1
                time.sleep(0.5)
        if not text:
            print("[scraper] Пропуск элемента выгрузки: не удалось прочитать текст (stale).")
            continue

        try:
            snapshot_dt = _parse_snapshot_dt(text)
        except ValueError:
            print(f"[scraper] Не удалось распарсить дату/время из строки: {text!r}")
            continue

        title = text

        # Если передан колбэк проверки, спрашиваем, нужно ли скачивать этот срез
        if should_download is not None and not should_download(title, snapshot_dt):
            continue

        # Кнопка скачивания
        download_btn = item.find_element(By.CSS_SELECTOR, download_selector)
        before_files = set(download_dir.glob("*.xlsx"))
        before_files |= existing_files

        download_btn.click()

        file_path = _wait_for_new_file(download_dir, before_files)
        existing_files.add(file_path)

        export_item = ExportItem(title=title, snapshot_dt=snapshot_dt, file_path=file_path)
        results.append(export_item)

        # Если передан колбэк обработки — вызываем его сразу после загрузки файла
        if on_export is not None:
            on_export(export_item)

    return results


def create_and_download_latest_export(
    driver,
    config: Dict[str, Any],
    download_dir: Path,
    should_download: Optional[Callable[[str, datetime], bool]] = None,
    on_export: Optional[Callable[[ExportItem], None]] = None,
) -> Optional[ExportItem]:
    """
    Создает новую выгрузку через кнопку внизу модалки и дожидается,
    пока для неё появится кнопка скачивания.
    После этого скачивает и (опционально) передаёт ExportItem в on_export.
    """
    modal_cfg = config.get("modal", {})
    item_selector = modal_cfg.get("item_selector")
    text_selector = modal_cfg.get("item_text_selector")
    download_selector = modal_cfg.get("download_button_selector")
    panel_selector = modal_cfg.get("new_export_panel_selector", "div.r-modal-panel__bottom")
    panel_button_selector = modal_cfg.get("new_export_button_selector", "button")

    if not (item_selector and text_selector and download_selector):
        raise ValueError(
            "Для режима создания новой выгрузки в modal должны быть заданы "
            "item_selector, item_text_selector и download_button_selector."
        )

    wait = WebDriverWait(
        driver, int(config.get("browser", {}).get("explicit_wait", 20))
    )

    # Запоминаем, какие элементы уже есть
    existing_items = driver.find_elements(By.CSS_SELECTOR, item_selector)
    existing_texts = {el.text.strip() for el in existing_items if el.text.strip()}

    # Нажимаем кнопку "Начать экспорт" внизу модалки
    try:
        panel = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, panel_selector))
        )
        start_btn = panel.find_element(By.CSS_SELECTOR, panel_button_selector)
        start_btn.click()
    except TimeoutException as exc:
        raise RuntimeError(
            "Не удалось найти или нажать кнопку создания новой выгрузки. "
            f"modal.new_export_panel_selector={panel_selector!r}."
        ) from exc

    # Ждём появления нового элемента export-item
    deadline = time.time() + 300  # максимум 5 минут
    new_item = None
    new_text = None

    while time.time() < deadline:
        current_items = driver.find_elements(By.CSS_SELECTOR, item_selector)
        for it in current_items:
            try:
                txt = it.text.strip()
            except StaleElementReferenceException:
                # Элемент успел протухнуть — пропускаем его и двигаемся дальше.
                continue
            if txt and txt not in existing_texts:
                new_item = it
                new_text = txt
                break
        if new_item is not None:
            break
        time.sleep(5)

    if new_item is None:
        raise TimeoutError("Не удалось дождаться появления новой выгрузки.")

    # Ждём появления кнопки скачивания внутри нового элемента
    download_btn = None
    while time.time() < deadline:
        try:
            btns = new_item.find_elements(By.CSS_SELECTOR, download_selector)
        except StaleElementReferenceException:
            # Элемент мог пересоздаться, ищем его заново по тексту
            current_items = driver.find_elements(By.CSS_SELECTOR, item_selector)
            for it in current_items:
                if it.text.strip() == new_text:
                    new_item = it
                    break
            continue

        for b in btns:
            if b.is_displayed() and b.is_enabled():
                download_btn = b
                break

        if download_btn is not None:
            break

        time.sleep(5)

    if download_btn is None:
        raise TimeoutError(
            "Не удалось дождаться кнопки скачивания для новой выгрузки."
        )

    # Обрабатываем только эту новую выгрузку.
    # Элемент и его текст тоже могут стать "stale", поэтому добавляем защиту.
    retries = 3
    text = ""
    while retries > 0:
        try:
            text_el = new_item.find_element(By.CSS_SELECTOR, text_selector)
            text = text_el.text.strip()
            break
        except StaleElementReferenceException:
            retries -= 1
            # Переищем new_item по тексту, если он пересоздался
            current_items = driver.find_elements(By.CSS_SELECTOR, item_selector)
            for it in current_items:
                if it.text.strip() == (new_text or ""):
                    new_item = it
                    break
            time.sleep(0.5)

    if not text:
        raise RuntimeError(
            "Не удалось прочитать текст новой выгрузки (stale element). "
            "Попробуйте повторить запуск или уточнить селекторы в конфиге."
        )

    snapshot_dt = _parse_snapshot_dt(text)
    title = text

    if should_download is not None and not should_download(title, snapshot_dt):
        return None

    before_files = set(download_dir.glob("*.xlsx"))
    download_btn.click()

    file_path = _wait_for_new_file(download_dir, before_files)

    export_item = ExportItem(title=title, snapshot_dt=snapshot_dt, file_path=file_path)

    if on_export is not None:
        on_export(export_item)

    return export_item


def run_scraper(
    config_path: str = "scraper_config.yaml",
    *,
    should_download: Optional[Callable[[str, datetime], bool]] = None,
    on_export: Optional[Callable[[ExportItem], None]] = None,
) -> List[ExportItem]:
    """
    Режим «bulk»:
    1) логинится;
    2) открывает модалку экспорта и прокручивает всю историю;
    3) скачивает все выгрузки (в порядке от старых к новым) и для каждой
       по желанию вызывает on_export.
    """
    print(f"[scraper] Загрузка конфига из {config_path!r}")
    config = load_config(config_path)
    driver, download_dir = _build_driver(config)

    try:
        print("[scraper] Шаг 1/3: логин...")
        login(driver, config)
        print("[scraper] Шаг 2/3: открытие страницы экспорта и модального окна...")
        open_export_modal(driver, config)
        print("[scraper] Шаг 3/3: прокрутка истории выгрузок...")
        load_full_history(driver, config)
        print("[scraper] Сбор списка выгрузок и скачивание файлов...")
        exports = collect_and_download_exports(
            driver,
            config,
            download_dir,
            should_download=should_download,
            on_export=on_export,
        )
    finally:
        driver.quit()

    return exports


def run_scraper_latest(
    config_path: str = "scraper_config.yaml",
    *,
    should_download: Optional[Callable[[str, datetime], bool]] = None,
    on_export: Optional[Callable[[ExportItem], None]] = None,
) -> Optional[ExportItem]:
    """
    Режим «latest»:
    1) логинится;
    2) открывает модалку экспорта;
    3) создаёт новую выгрузку (кнопка в r-modal-panel__bottom);
    4) ждёт появления новой строки и кнопки скачивания;
    5) скачивает и обрабатывает только эту выгрузку.
    """
    print(f"[scraper] (latest) Загрузка конфига из {config_path!r}")
    config = load_config(config_path)
    driver, download_dir = _build_driver(config)

    try:
        print("[scraper] (latest) Шаг 1/2: логин...")
        login(driver, config)
        print("[scraper] (latest) Шаг 2/2: открытие страницы экспорта и модального окна...")
        open_export_modal(driver, config)
        export_item = create_and_download_latest_export(
            driver,
            config,
            download_dir,
            should_download=should_download,
            on_export=on_export,
        )
    finally:
        driver.quit()

    return export_item

