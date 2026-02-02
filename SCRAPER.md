## Скрипт для автоматического импорта выгрузок из Атлас

### Требования

- Установленный браузер Chrome или Edge.
- Установлены зависимости из `requirements.txt` (в том числе `selenium`, `webdriver-manager`, `PyYAML`).

### Установка Chrome на сервере (Ubuntu/Debian)

На headless-сервере без GUI рекомендуется использовать **Chrome for Testing** — специальную сборку для автоматизации.

#### 1. Установка системных зависимостей

```bash
apt-get update && apt-get install -y \
    libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libasound2t64 libpango-1.0-0 libcairo2 libnss3 libnspr4 \
    wget unzip
```

> **Примечание:** На Ubuntu < 24.04 используйте `libasound2` вместо `libasound2t64`.

#### 2. Скачивание Chrome for Testing

Найдите актуальную версию на [Chrome for Testing](https://googlechromelabs.github.io/chrome-for-testing/) и скачайте:

```bash
# Создаём директорию для Chrome
mkdir -p /var/www/history_atlas/AtlasApplicationHistory/.chrome
cd /var/www/history_atlas/AtlasApplicationHistory/.chrome

# Скачиваем Chrome (замените версию на актуальную)
CHROME_VERSION="145.0.7632.26"
wget -q "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chrome-linux64.zip"
unzip chrome-linux64.zip && rm chrome-linux64.zip

# Скачиваем совместимый ChromeDriver
wget -q "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chromedriver-linux64.zip"
unzip chromedriver-linux64.zip && rm chromedriver-linux64.zip
```

#### 3. Установка прав на выполнение

```bash
chmod +x .chrome/chrome-linux64/chrome
chmod +x .chrome/chrome-linux64/chrome_crashpad_handler
chmod +x .chrome/chromedriver-linux64/chromedriver
```

#### 4. Проверка установки

```bash
.chrome/chrome-linux64/chrome --version
# Должно вывести: Google Chrome for Testing 145.0.7632.26
```

#### 5. Настройка конфига

В `scraper_config.yaml` укажите путь к бинарю:

```yaml
browser:
  driver: "chrome"
  binary_path: "/var/www/history_atlas/AtlasApplicationHistory/.chrome/chrome-linux64/chrome"
  headless: true
```

ChromeDriver будет найден автоматически в соседней папке `chromedriver-linux64`.

### Настройка конфигурации

В корне проекта находится файл `scraper_config.yaml`. В нём нужно указать:

- `auth` — адрес страницы логина, логин/пароль и CSS‑селекторы полей и кнопки входа.
- `pages` — URL страницы, где доступен экспорт, текст пункта меню/ссылки «Экспорт по выбранным фильтрам» и селектор модального окна.
- `modal` — селекторы контейнера списка выгрузок, отдельного элемента списка, текста (с датой/временем) и кнопки скачивания.
- `browser` — тип драйвера (`chrome` или `edge`), папка загрузки файлов, таймауты, максимальное количество прокруток и режим headless.

Дополнительные опции в секции `browser`:

- `headless` — `true/false`, по умолчанию `true`. На сервере обычно оставляем `true`.
- `binary_path` — явный путь до бинаря браузера (например, `/snap/bin/chromium`), если он не находится автоматически.

Пример структуры см. в самом файле `scraper_config.yaml`.

### Запуск скрапера

Команда для запуска из корня проекта:

```bash
python manage.py fetch_exports
```

Дополнительные параметры:

- `--config path/to/config.yaml` — путь к альтернативному конфигу.
- `--limit N` — ограничить количество выгрузок, которые будут скачаны и импортированы за один запуск.

Скрапер:

1. Авторизуется на платформе.
2. Открывает страницу экспорта и модальное окно «Экспорт по выбранным фильтрам».
3. Прокручивает историю выгрузок до конца.
4. Скачивает все найденные файлы.
5. Для каждого файла вызывает существующую логику импорта (`import_from_file`), которая обновляет заявки и записывает историю импортов.


