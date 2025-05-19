"""
Основной файл Flask-приложения для нашего мультисервисного портала.

Этот модуль отвечает за создание веб-страниц и API-интерфейсов
для набора полезных онлайн-инструментов. Каждый сервис имеет свою
интерактивную страницу для удобного использования прямо в браузере.

Текущий список сервисов:
- Список Задач (To-Do List)
- Сокращатель URL-адресов
- Цитаты дня (и факты)
- Каталог книг и фильмов
- Простой онлайн-калькулятор
- Генератор случайных чисел и паролей

Важное замечание: на данный момент все данные сервисов хранятся только
в оперативной памяти сервера и будут утеряны при его перезапуске.
В будущем планируется переход на полноценную базу данных.
"""
from functools import wraps
import datetime
import random
import string
import json # Если понадобится json.dumps для более сложного форматирования

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

# Инициализация основного экземпляра Flask-приложения.
# Использование `__name__` помогает Flask правильно определять пути к шаблонам и статическим файлам.
app = Flask(__name__)

# --- Настройки конфигурации приложения ---
# Обеспечиваем корректное отображение кириллицы и других не-ASCII символов в JSON-ответах.
app.config['JSON_AS_ASCII'] = False
# Включаем форматированный (pretty-print) вывод JSON для удобства чтения во время разработки.
# Для боевого сервера это можно отключить для экономии трафика.
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

# --- Контекстный процессор: делаем переменные доступными во всех шаблонах ---
@app.context_processor
def inject_global_template_vars():
    """
    Внедряет переменные, которые должны быть доступны во всех HTML-шаблонах.
    В данном случае, добавляем `current_year` для отображения в футере.
    """
    return {'current_year': datetime.datetime.now().year}

# --- Внутрисерверные хранилища данных (временно, в оперативной памяти) ---
# TODO: Критически важно! Заменить эти in-memory хранилища на базу данных
#       (например, SQLite для простоты или PostgreSQL для масштабируемости)
#       для обеспечения постоянства данных между перезапусками сервера.

# Сервис 1: Список Задач (To-Do List)
tasks_db = []  # Более "базоподобное" имя вместо tasks_data
_next_task_id_counter = 1 # Явное указание, что это счетчик

# Сервис 2: Сокращатель URL-адресов
url_shortener_mappings = {} # Более описательное имя

# Сервис 3: Цитаты дня
quotes_collection = [ # "Коллекция" звучит лучше для набора цитат
    {"id": 1, "text": "Жизнь - это то, что с тобой происходит, пока ты строишь другие планы.", "author": "Джон Леннон"},
    {"id": 2, "text": "Единственный способ делать великие дела – любить то, что вы делаете.", "author": "Стив Джобс"},
    {"id": 3, "text": "Чтобы дойти до цели, надо прежде всего идти.", "author": "Оноре де Бальзак"}
]
_next_quote_id_counter = 4

# Учетные данные для Basic Authentication (только для добавления цитат)
# ВАЖНО: В реальном приложении эти данные НИКОГДА не должны храниться в коде.
#        Используйте переменные окружения и хеширование паролей.
BASIC_AUTH_USERNAME = 'admin' # ЗАМЕНИТЬ на безопасное значение из переменных окружения
BASIC_AUTH_PASSWORD = 'supersecretpassword123' # ЗАМЕНИТЬ и использовать хеширование

# Сервис 4: Каталог книг и фильмов
media_catalog_db = [
    {"id": 1, "type": "book", "title": "1984", "author": "Джордж Оруэлл", "year": 1949, "genre": "Антиутопия"},
    {"id": 2, "type": "movie", "title": "Начало", "director": "Кристофер Нолан", "year": 2010, "genre": "Научная фантастика"},
    {"id": 3, "type": "book", "title": "Мастер и Маргарита", "author": "Михаил Булгаков", "year": 1967, "genre": "Роман"},
]
_next_catalog_item_id_counter = 4

# Сервисы 5 (Калькулятор) и 6 (Генератор) не требуют серверного хранения состояния,
# вся логика их API stateless (обрабатывается в рамках одного запроса).

# --- Вспомогательные (утилитные) функции ---

def generate_random_short_code(length=6):
    """
    Создает случайную алфавитно-цифровую строку заданной длины.
    Используется в качестве короткого кода для сервиса сокращения URL.

    Args:
        length (int): Желаемая длина короткого кода. По умолчанию 6.

    Returns:
        str: Сгенерированный короткий код.
    """
    # Используем буквы ASCII (верхний и нижний регистр) и цифры для кода.
    possible_chars = string.ascii_letters + string.digits
    # Собираем строку из случайно выбранных символов.
    return ''.join(random.choice(possible_chars) for _ in range(length))

# --- Функционал Basic Authentication ---
def verify_credentials(username, password):
    """Простая проверка учетных данных для Basic Auth."""
    return username == BASIC_AUTH_USERNAME and password == BASIC_AUTH_PASSWORD

def require_authentication_response():
    """
    Формирует и возвращает стандартный HTTP-ответ 401 Unauthorized,
    предлагающий клиенту пройти Basic Authentication.
    """
    error_message = {
        'error': "Аутентификация не пройдена.",
        'message': "Для доступа к этому ресурсу необходимы имя пользователя и пароль."
    }
    response = jsonify(error_message)
    response.status_code = 401
    # 'WWW-Authenticate' заголовок инициирует диалог Basic Auth в браузере.
    response.headers['WWW-Authenticate'] = 'Basic realm="Доступ к этому разделу требует аутентификации"'
    return response

def protected_by_auth(function_to_protect):
    """
    Декоратор для защиты маршрутов (эндпоинтов) с помощью Basic Authentication.
    Если аутентификация не проходит, возвращает ответ 401.

    Args:
        function_to_protect: Декорируемая функция (обработчик маршрута).

    Returns:
        function: Обёрнутая функция с проверкой аутентификации.
    """
    @wraps(function_to_protect)
    def decorated_view(*args, **kwargs):
        auth_details = request.authorization # Flask предоставляет данные из заголовка Authorization
        if not auth_details or not verify_credentials(auth_details.username, auth_details.password):
            # Если данные не предоставлены или неверны, отправляем ответ 401.
            return require_authentication_response()
        # Если аутентификация успешна, вызываем оригинальную функцию.
        return function_to_protect(*args, **kwargs)
    return decorated_view

# --- Маршруты для отображения HTML-страниц ---

@app.route('/')
def home_page():
    """Отображает главную (лендинговую) страницу сайта."""
    # Заголовок страницы, который будет отображаться в теге <title> и, возможно, в хедере.
    page_specific_title = 'Добро пожаловать на МногоСервисПроект!'
    return render_template('index.html', page_title=page_specific_title)

@app.route('/services')
def list_all_services_page(): # Описательное имя
    """Отображает страницу со списком всех доступных на сайте сервисов."""
    # Список сервисов, который будет передан в шаблон для генерации виджетов.
    # Используем url_for для построения URL – это гарантирует, что ссылки
    # останутся рабочими даже если мы изменим пути в @app.route.
    services_summary = [
        {"name": "Список задач (To-Do List)", "url": url_for('service_todo_page'), "description": "Ваш личный менеджер задач. Создавайте, отслеживайте и достигайте целей"},
        {"name": "Сокращатель URL-адресов", "url": url_for('service_shortener_page'), "description": "Укоротите любую ссылку. Быстро, просто и удобно для распространения"},
        {"name": "Цитаты дня и Факты", "url": url_for('service_quote_page'), "description": "Ваша ежедневная порция мудрости и знаний. Вдохновляйтесь и расширяйте кругозор"},
        {"name": "Каталог книг и фильмов", "url": url_for('service_catalog_page'), "description": "Сохраните воспоминания о лучших книгах и фильмах. Ваша личная история чтения и просмотров"},
        {"name": "Простой калькулятор", "url": url_for('service_calculator_page'), "description": "Мгновенные арифметические вычисления без лишних сложностей"},
        {"name": "Генератор случайных данных", "url": url_for('service_random_page'), "description": "Положитесь на волю случая! Сгенерируйте случайные числа или создайте уникальный пароль в один клик"},
        {"name": "Конвертер единиц измерения", "url": url_for('service_converter_page'), "description": "Конвертируйте различные единицы длины, объёма и размера данных."}
    ]
    return render_template('services.html', services=services_summary, page_title="Наши онлайн-сервисы")

@app.route('/service/todo')
def service_todo_page():
    """Отображает интерактивную страницу для сервиса 'Список Задач' и документацию по его API."""
    service_page_data = {
        "name": "Список задач (To-Do List)",
        "intro": "Наш 'Список задач' поможет вам легко навести порядок в делах! Добавляйте новые задачи всего в пару кликов, просматривайте то, что актуально сейчас, отмечайте выполненное и с чувством удовлетворения удаляйте завершенные дела. Вы можете удобно работать со своими задачами прямо на этой странице, используя интерактивный интерфейс ниже. А если вы разработчик, наш API готов к интеграции с вашими приложениями.",
        "page_url_name": "service_todo_page", # Может использоваться для активной навигации
        "endpoints": [
            {"method": "POST", "path": url_for('tasks_api_create'), "description": "Создать новую задачу.", "example_request": {"text": "Прочитать главу книги"}},
            {"method": "GET", "path": url_for('tasks_api_get_all'), "description": "Получить текущий список всех задач."},
            {"method": "GET", "path": "/api/tasks/<id>", "description": "Получить детальную информацию о конкретной задаче по её ID."},
            {"method": "PUT", "path": "/api/tasks/<id>", "description": "Обновить существующую задачу (например, изменить текст или отметить как выполненную).", "example_request": {"text": "Прочитать две главы книги", "done": False}},
            {"method": "DELETE", "path": "/api/tasks/<id>", "description": "Удалить задачу из списка по её ID."}
        ]
    }
    return render_template('service_todo.html', service_data=service_page_data, page_title=service_page_data["name"])

@app.route('/service/shortener')
def service_shortener_page():
    """Отображает интерактивную страницу для сервиса 'Сокращатель URL' и документацию по API."""
    service_page_data = {
        "name": "Сокращатель URL-адресов",
        "intro": "Устали от бесконечных и сложных веб-ссылок? Наш 'Сокращатель URL' мигом превратит любую длинную ссылку в короткую, аккуратную и легко запоминающуюся. Просто вставьте ваш адрес в поле ниже, нажмите кнопку, и получите элегантную короткую версию для удобного обмена.",
        "page_url_name": "service_shortener_page",
        "endpoints": [
            {"method": "POST", "path": url_for('url_shortener_api_create'), "description": "Сократить предоставленный URL-адрес.", "example_request": {"long_url": "https://www.example.com/путь/к/очень/длинному/и/сложному/ресурсу"}},
            {"method": "GET", "path": "/s/<short_code>", "description": "Перенаправление на оригинальный URL при переходе по короткой ссылке (например, /s/xYz123). Обратите внимание на префикс /s/."},
        ]
    }
    return render_template('service_shortener.html', service_data=service_page_data, page_title=service_page_data["name"])

@app.route('/service/quote')
def service_quote_page():
    """Отображает интерактивную страницу для сервиса 'Цитаты Дня' и документацию по API."""
    service_page_data = {
        "name": "Цитаты дня и факты",
        "intro": "Ищете немного вдохновения или хотите блеснуть интересным фактом? Наш сервис 'Цитаты дня и факты' – то, что вам нужно! Получайте случайную мудрую мысль или занимательный факт, либо находите конкретную запись по её номеру (ID). Если вы хотите пополнить нашу коллекцию, API для добавления новых цитат доступен для разработчиков (требуется простая Basic Authentication с учетными данными: admin / supersecretpassword123 – для тестовых целей, конечно!).",
        "page_url_name": "service_quote_page",
        "endpoints": [
            {"method": "GET", "path": url_for('quotes_api_get_random'), "description": "Получить случайную цитату или факт из коллекции."},
            {"method": "GET", "path": "/api/quotes/<id>", "description": "Получить конкретную цитату или факт по её уникальному ID."}, # Изменил путь для консистентности с другими ID-based
            {"method": "POST", "path": url_for('quotes_api_add_new'), "description": "Добавить новую цитату в коллекцию (требуется Basic Authentication).", "example_request": {"text": "Великие умы обсуждают идеи; средние умы обсуждают события; мелкие умы обсуждают людей.", "author": "Элеонора Рузвельт"}}
        ]
    }
    return render_template('service_quote.html', service_data=service_page_data, page_title=service_page_data["name"])

@app.route('/service/catalog')
def service_catalog_page():
    """Отображает интерактивную страницу для 'Каталога Книг и Фильмов' и документацию по API."""
    service_page_data = {
        "name": "Каталог книг и фильмов",
        "intro": "Любите книги и кино? Наш 'Каталог' поможет вам создать и упорядочить вашу личную медиатеку! Легко добавляйте информацию о прочитанных книгах и просмотренных фильмах, ведите учет своей коллекции и быстро находите нужные произведения с помощью удобных фильтров. Ваша библиотека впечатлений – теперь в полном порядке!",
        "page_url_name": "service_catalog_page",
        "endpoints": [
            {"method": "POST", "path": url_for('catalog_api_add_item'), "description": "Добавить новый элемент (книгу или фильм) в каталог.", "example_request": {"type": "book", "title": "Автостопом по галактике", "author": "Дуглас Адамс", "year": 1979, "genre":"Научная фантастика"}},
            {"method": "GET", "path": url_for('catalog_api_get_items'), "description": "Получить список всех элементов каталога. Поддерживается фильтрация по GET-параметрам: ?type=book&author=...&year=...&genre=...&title=...&creator=..."},
            {"method": "GET", "path": "/api/catalog/<id>", "description": "Получить детальную информацию об элементе каталога по его ID."}
        ]
    }
    return render_template('service_catalog.html', service_data=service_page_data, page_title=service_page_data["name"])

@app.route('/service/calculator')
def service_calculator_page():
    """Отображает интерактивную страницу 'Калькулятора' и документацию по его API."""
    service_page_data = {
        "name": "Простой онлайн-калькулятор",
        "intro": "Нужно быстро что-то посчитать? Наш 'Простой онлайн-калькулятор' справится с основными арифметическими задачами: сложением, вычитанием, умножением и делением. Просто воспользуйтесь удобной интерактивной панелью ниже! А для разработчиков, как всегда, доступен наш API для интеграции калькулятора в другие проекты.",
        "page_url_name": "service_calculator_page",
        "endpoints": [
            {"method": "GET", "path": f"{url_for('calculator_api_process')}?num1=X&num2=Y&operation=OP", "description": "Выполнить операцию. 'OP' может быть: add, subtract, multiply, divide."},
            {"method": "POST", "path": url_for('calculator_api_process'), "description": "Тело запроса в формате JSON: {\"num1\": X, \"num2\": Y, \"operation\": \"OP\"}", "example_request": {"num1": 25, "num2": 4, "operation": "multiply"}}
        ]
    }
    return render_template('service_calculator.html', service_data=service_page_data, page_title=service_page_data["name"])

@app.route('/service/random')
def service_random_page():
    """Отображает интерактивную страницу 'Генератора случайных данных' и документацию по его API."""
    service_page_data = {
        "name": "Генератор случайных данных",
        "intro": "Нужна доля случайности? Наш 'Генератор случайных данных' к вашим услугам! Он поможет создать случайные числа в нужном вам диапазоне – идеально для игр, тестов или просто для принятия непредвзятого решения. А еще вы можете сгенерировать надежный пароль, указав желаемую длину и необходимость использования специальных символов, чтобы повысить безопасность ваших аккаунтов.",
        "page_url_name": "service_random_page",
        "endpoints": [
            {"method": "GET", "path": f"{url_for('random_data_api_get_number')}?min=X&max=Y", "description": "Генерация случайного целого числа в диапазоне от X до Y."},
            {"method": "GET", "path": f"{url_for('random_data_api_get_password')}?length=L&use_symbols=true/false", "description": "Генерация случайного пароля указанной длины."}
        ]
    }
    return render_template('service_random.html', service_data=service_page_data, page_title=service_page_data["name"])


# --- API Эндпоинты ---
# Переименовал функции API для большей ясности и чтобы избежать конфликтов имен.

# Сервис 1: Список Задач (To-Do List) - API
@app.route('/api/tasks', methods=['POST'])
def tasks_api_create():
    """API: Создает новую задачу."""
    global _next_task_id_counter
    if not request.is_json:
        return jsonify({"error": "Некорректный формат запроса: ожидается JSON."}), 400
    
    json_data = request.get_json()
    task_description_text = json_data.get('text')

    if not task_description_text or not isinstance(task_description_text, str) or not task_description_text.strip():
        return jsonify({"error": "Поле 'text' для задачи обязательно и не может быть пустым."}), 400
    
    new_task_item = {
        'id': _next_task_id_counter,
        'text': task_description_text.strip(),
        'done': False # Новые задачи по умолчанию не выполнены
    }
    tasks_db.append(new_task_item)
    _next_task_id_counter += 1
    
    return jsonify({'message': 'Задача успешно создана.', 'task': new_task_item}), 201

@app.route('/api/tasks', methods=['GET'])
def tasks_api_get_all():
    """API: Возвращает список всех задач."""
    return jsonify({'count': len(tasks_db),'tasks': tasks_db})

@app.route('/api/tasks/<int:task_id>', methods=['GET'])
def tasks_api_get_one(task_id: int):
    """API: Возвращает одну задачу по ее ID."""
    found_task = next((task for task in tasks_db if task['id'] == task_id), None)
    if found_task is None:
        return jsonify({"error": f"Задача с идентификатором {task_id} не найдена."}), 404
    return jsonify({'task': found_task})

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def tasks_api_update_one(task_id: int):
    """API: Обновляет существующую задачу (текст и/или статус выполнения)."""
    task_to_modify = next((task for task in tasks_db if task['id'] == task_id), None)
    if task_to_modify is None:
        return jsonify({"error": f"Задача с ID {task_id} не найдена и не может быть обновлена."}), 404
    
    if not request.is_json:
        return jsonify({"error": "Тело запроса для обновления должно быть в формате JSON."}), 400
    
    update_data = request.get_json()
    fields_updated_count = 0

    if 'text' in update_data:
        new_text = update_data['text']
        if isinstance(new_text, str) and new_text.strip():
            task_to_modify['text'] = new_text.strip()
            fields_updated_count += 1
        elif new_text is not None: # Если text передан, но он невалидный
             app.logger.warning(f"При обновлении задачи {task_id} получено невалидное значение для 'text': {new_text}")
             # Можно вернуть ошибку 400, если это строгое требование.
             # return jsonify({"error": "Если поле 'text' передано, оно должно быть непустой строкой."}), 400
    
    if 'done' in update_data:
        new_status = update_data['done']
        if isinstance(new_status, bool):
            task_to_modify['done'] = new_status
            fields_updated_count += 1
        elif new_status is not None: # Если done передано, но не булево
            app.logger.warning(f"При обновлении задачи {task_id} получено невалидное значение для 'done': {new_status}")
            # return jsonify({"error": "Если поле 'done' передано, оно должно быть булевым значением (true/false)."}), 400

    if fields_updated_count == 0 and update_data: # Если тело запроса было, но ничего валидного не найдено
        return jsonify({"message": "Не было предоставлено валидных данных для обновления.", 'task': task_to_modify}), 200 # или 400, если это считать ошибкой клиента
        
    return jsonify({'message': f'Задача {task_id} была успешно обновлена.', 'task': task_to_modify})

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def tasks_api_delete_one(task_id: int):
    """API: Удаляет задачу по ее ID."""
    global tasks_db # Так как мы модифицируем сам список
    
    original_length = len(tasks_db)
    tasks_db = [task for task in tasks_db if task['id'] != task_id]
    
    if len(tasks_db) == original_length: # Значит, задача не была найдена и удалена
        return jsonify({"error": f"Задача с идентификатором {task_id} не найдена для удаления."}), 404
        
    # Статус 200 OK с сообщением или 204 No Content с пустым телом. Выберем 200 для единообразия с сообщением.
    return jsonify({"message": f"Задача {task_id} успешно удалена из списка."}), 200

# Сервис 2: Сокращатель URL - API
@app.route('/api/shorten', methods=['POST'])
def url_shortener_api_create():
    """API: Создает короткую ссылку для переданного длинного URL."""
    if not request.is_json:
        return jsonify({'error': 'Тело запроса должно быть в формате JSON.'}), 400
    
    data = request.get_json()
    original_long_url = data.get('long_url')

    if not original_long_url or not isinstance(original_long_url, str):
        return jsonify({'error': 'Обязательное поле "long_url" отсутствует или имеет неверный тип (ожидается строка).'}), 400
    
    # TODO: Реализовать более строгую валидацию URL, например, с использованием urllib.parse.
    #       Например, `from urllib.parse import urlparse; parsed = urlparse(original_long_url); if not (parsed.scheme and parsed.netloc): ...`

    # Проверка на существующие сокращения для данного URL – для избежания дублирования.
    for short_code, mapped_url in url_shortener_mappings.items():
        if mapped_url == original_long_url:
            # Формируем полный URL для уже существующей короткой ссылки.
            # request.host_url обычно включает слеш в конце, например, 'http://127.0.0.1:5001/'
            # url_for('redirect_by_short_code', ...) вернет '/s/short_code'
            # Убираем лишний слеш, если он есть.
            full_existing_short_url = request.host_url.rstrip('/') + url_for('redirect_by_short_code', short_code=short_code)
            return jsonify({
                'message': 'Этот URL уже был сокращен ранее.',
                'short_url': full_existing_short_url,
                'original_url': original_long_url
            }), 200 # 200 OK, так как ресурс уже существует.

    generated_code = generate_random_short_code()
    # Цикл для гарантии уникальности кода (маловероятно при длине 6, но лучшая практика).
    # Ограничим количество попыток, чтобы избежать бесконечного цикла в теории.
    MAX_CODE_GENERATION_ATTEMPTS = 10 
    current_attempt = 0
    while generated_code in url_shortener_mappings and current_attempt < MAX_CODE_GENERATION_ATTEMPTS:
        generated_code = generate_random_short_code()
        current_attempt += 1
    
    if generated_code in url_shortener_mappings:
        # Этот сценарий очень маловероятен с достаточной длиной кода.
        app.logger.error("Не удалось сгенерировать уникальный короткий код для URL после нескольких попыток.")
        return jsonify({'error': 'Внутренняя ошибка сервера: не удалось создать короткую ссылку. Пожалуйста, попробуйте позже.'}), 500
    
    url_shortener_mappings[generated_code] = original_long_url
    # Формируем полный короткий URL для ответа клиенту.
    # Используем /s/ префикс для коротких ссылок, чтобы они не конфликтовали с другими маршрутами.
    full_new_short_url = request.host_url.rstrip('/') + url_for('redirect_by_short_code', short_code=generated_code)
    
    return jsonify({
        'message': 'URL-адрес успешно сокращен!',
        'short_url': full_new_short_url,
        'original_url': original_long_url
    }), 201

@app.route('/s/<short_code>', methods=['GET']) # Изменен маршрут на /s/ для ясности
def redirect_by_short_code(short_code: str):
    """Перенаправляет с короткого URL на оригинальный длинный URL."""
    destination_url = url_shortener_mappings.get(short_code)
    
    if destination_url:
        # TODO: Добавить логирование переходов или подсчет статистики использования ссылок.
        app.logger.info(f"Редирект: короткий код '{short_code}' -> '{destination_url}'")
        return redirect(destination_url, code=302) # 302 Found - стандарт для временного редиректа.
    else:
        # FIXME: Возможно, стоит рендерить красивую HTML-страницу 404, а не JSON,
        #        так как по этой ссылке будут переходить обычные пользователи.
        return jsonify({'error': f'Короткая ссылка с кодом "{short_code}" не найдена или устарела.'}), 404

# Сервис 3: Цитаты дня - API
@app.route('/api/quotes', methods=['POST']) # Изменил путь на /api/quotes для REST-подобности
@protected_by_auth # Этот эндпоинт защищен Basic Authentication.
def quotes_api_add_new():
    """API: Добавляет новую цитату в коллекцию (требует аутентификации)."""
    global _next_quote_id_counter
    if not request.is_json:
        return jsonify({"error": "Запрос должен быть в формате JSON."}), 400
    
    data = request.get_json()
    quote_text = data.get("text")
    # Если автор не указан, или указана пустая строка, используем "Аноним".
    quote_author = data.get("author", "Аноним").strip()
    if not quote_author: # Если после strip осталась пустая строка
        quote_author = "Аноним"

    if not quote_text or not isinstance(quote_text, str) or not quote_text.strip():
        return jsonify({"error": "Поле 'text' для цитаты является обязательным и не может быть пустым."}), 400
    
    # Предотвращение дублирования (опционально, но полезно)
    # for existing_quote in quotes_collection:
    #     if existing_quote["text"].lower() == quote_text.lower() and existing_quote["author"].lower() == quote_author.lower():
    #         return jsonify({"warning": "Такая цитата от этого автора уже существует.", "quote": existing_quote}), 409 # Conflict

    new_quote_entry = {
        "id": _next_quote_id_counter,
        "text": quote_text.strip(),
        "author": quote_author # Уже .strip() выше
    }
    quotes_collection.append(new_quote_entry)
    _next_quote_id_counter += 1
    return jsonify({'message': 'Цитата успешно добавлена в коллекцию.', 'quote': new_quote_entry}), 201

@app.route('/api/quotes/random', methods=['GET']) # Путь /api/quotes/random
def quotes_api_get_random():
    """API: Возвращает случайную цитату из имеющихся."""
    if not quotes_collection:
        return jsonify({"error": "В данный момент нет доступных цитат для отображения."}), 404 # Not Found
    
    randomly_selected_quote = random.choice(quotes_collection)
    return jsonify(randomly_selected_quote)

@app.route('/api/quotes/<int:quote_id>', methods=['GET']) # Путь /api/quotes/<id>
def quotes_api_get_one_by_id(quote_id: int):
    """API: Возвращает цитату по ее уникальному идентификатору."""
    found_quote = next((q for q in quotes_collection if q['id'] == quote_id), None)
    if found_quote:
        return jsonify(found_quote)
    else:
        return jsonify({"error": f"Цитата с идентификатором {quote_id} не найдена в коллекции."}), 404

# Сервис 4: Каталог книг и фильмов - API
@app.route('/api/catalog', methods=['POST'])
def catalog_api_add_item():
    """API: Добавляет новый элемент (книгу или фильм) в медиа-каталог."""
    global _next_catalog_item_id_counter
    if not request.is_json:
        return jsonify({"error": "Тело запроса должно быть в формате JSON."}), 400
    
    data = request.get_json()
    
    item_type = data.get('type')
    title = data.get('title')
    year_str = data.get('year')
    genre = data.get("genre", "Не указан").strip() # Жанр опционален, по умолчанию "Не указан"

    # --- Валидация входных данных ---
    if not item_type or item_type not in ['book', 'movie']:
        return jsonify({"error": "Обязательное поле 'type' должно иметь значение 'book' или 'movie'."}), 400
    if not title or not isinstance(title, str) or not title.strip():
        return jsonify({"error": "Обязательное поле 'title' не может быть пустым."}), 400
    
    try:
        year = int(year_str) if year_str is not None else None # None если не передано
        # Проверка корректности года (реалистичные рамки)
        current_real_year = datetime.datetime.now().year
        # Позволяем указывать год на несколько лет вперед (для будущих релизов)
        if year is None or not (1800 <= year <= current_real_year + 10): 
             return jsonify({"error": f"Поле 'year' ({year_str}) содержит некорректное значение. Ожидается год в диапазоне 1800-{current_real_year + 10}."}), 400
    except ValueError: # Если year_str не может быть преобразован в int
        return jsonify({"error": f"Значение года '{year_str}' должно быть целым числом."}), 400

    new_catalog_entry = {
        "id": _next_catalog_item_id_counter,
        "type": item_type,
        "title": title.strip(),
        "year": year,
        "genre": genre if genre else "Не указан" # Убедимся, что пустая строка тоже станет "Не указан"
    }

    if item_type == 'book':
        author = data.get('author')
        if not author or not isinstance(author, str) or not author.strip():
            return jsonify({"error": "Для элемента типа 'book' обязательно указание автора (непустая строка в поле 'author')."}), 400
        new_catalog_entry['author'] = author.strip()
    elif item_type == 'movie':
        director = data.get('director')
        if not director or not isinstance(director, str) or not director.strip():
            return jsonify({"error": "Для элемента типа 'movie' обязательно указание режиссера (непустая строка в поле 'director')."}), 400
        new_catalog_entry['director'] = director.strip()
    
    # TODO: Рассмотреть возможность добавления уникальности (например, по title + author/director + year),
    #       чтобы избежать полного дублирования записей в каталоге.

    media_catalog_db.append(new_catalog_entry)
    _next_catalog_item_id_counter += 1
    return jsonify({'message': 'Новый элемент успешно добавлен в каталог.', 'item': new_catalog_entry}), 201

@app.route('/api/catalog', methods=['GET'])
def catalog_api_get_items():
    """
    API: Возвращает список элементов каталога.
    Поддерживает фильтрацию по GET-параметрам: type, author, director, year, genre, title, creator.
    """
    # Начинаем с полной копии каталога, которую будем фильтровать.
    filtered_results = list(media_catalog_db) 

    # Получаем параметры фильтрации из запроса.
    # `request.args.get` безопасно возвращает None, если параметр отсутствует.
    filter_type = request.args.get('type')
    filter_author = request.args.get('author', type=str) # type=str для приведения, если параметр есть
    filter_director = request.args.get('director', type=str)
    filter_year_str = request.args.get('year')
    filter_genre = request.args.get('genre', type=str)
    filter_title = request.args.get('title', type=str)
    filter_creator = request.args.get('creator', type=str) # Универсальный фильтр по автору ИЛИ режиссеру

    # Применяем фильтры последовательно.
    if filter_type:
        filtered_results = [item for item in filtered_results if item.get('type') == filter_type]
    
    # Для текстовых полей (автор, режиссер, жанр, название) используем поиск по части строки без учета регистра.
    if filter_author:
        filtered_results = [item for item in filtered_results if filter_author.lower() in item.get('author', '').lower()]
    if filter_director:
        filtered_results = [item for item in filtered_results if filter_director.lower() in item.get('director', '').lower()]
    if filter_genre:
        filtered_results = [item for item in filtered_results if filter_genre.lower() in item.get('genre', '').lower()]
    if filter_title:
        filtered_results = [item for item in filtered_results if filter_title.lower() in item.get('title', '').lower()]
    
    if filter_creator:
        creator_query = filter_creator.lower()
        filtered_results = [
            item for item in filtered_results if 
            (creator_query in item.get('author', '').lower()) or 
            (creator_query in item.get('director', '').lower())
        ]
    
    if filter_year_str:
        try:
            year_to_filter = int(filter_year_str)
            filtered_results = [item for item in filtered_results if item.get('year') == year_to_filter]
        except ValueError:
            # Если год передан, но он не является числом, можно либо игнорировать фильтр, либо вернуть ошибку.
            # Пока просто игнорируем, но можно добавить app.logger.warning или return jsonify(...) 400
            app.logger.info(f"Получен нечисловой параметр года для фильтрации каталога: {filter_year_str}")
            
    # API каталога часто возвращает напрямую список элементов, а не объект с ключом 'items'.
    return jsonify(filtered_results)

@app.route('/api/catalog/<int:item_id>', methods=['GET'])
def catalog_api_get_one_by_id(item_id: int):
    """API: Возвращает элемент каталога по его уникальному ID."""
    catalog_entry = next((item for item in media_catalog_db if item['id'] == item_id), None)
    if catalog_entry:
        return jsonify(catalog_entry)
    else:
        return jsonify({"error": f"Элемент каталога с идентификатором {item_id} не найден."}), 404

# Сервис 5: Калькулятор - API
@app.route('/api/calculate', methods=['GET', 'POST'])
def calculator_api_process():
    """
    API: Выполняет арифметическую операцию.
    Принимает два числа (num1, num2) и операцию (operation).
    Поддерживает GET-параметры и JSON-тело для POST-запросов.
    """
    input_data = {}
    request_source_info = "" # Для информативного ответа

    if request.method == 'GET':
        input_data = request.args.to_dict() # Преобразуем QueryArgs в обычный dict
        request_source_info = "GET-параметры"
    elif request.method == 'POST':
        if not request.is_json:
            return jsonify({"error": "Для POST-запросов ожидается тело в формате JSON."}), 400
        input_data = request.get_json()
        request_source_info = "JSON (тело запроса)"

    num1_str = input_data.get('num1')
    num2_str = input_data.get('num2')
    operation_name = input_data.get('operation')

    # Валидация наличия всех обязательных полей
    if None in [num1_str, num2_str, operation_name]: # Проверяем на None, а не только на falsy значения
        missing = [p for p in ['num1', 'num2', 'operation'] if input_data.get(p) is None]
        return jsonify({"error": f"Отсутствуют обязательные параметры: {', '.join(missing)}."}), 400

    # Отображение псевдонимов операций на символы для внутренней логики
    # и проверка корректности операции.
    operation_symbols_map = {
        'add': '+', '+': '+', 'сложение': '+', 'сложить': '+',
        'subtract': '-', '-': '-', 'вычитание': '-', 'вычесть': '-',
        'multiply': '*', '*': '*', 'умножение': '*', 'умножить': '*',
        'divide': '/', '/': '/', 'деление': '/', 'разделить': '/'
    }
    actual_operation_symbol = operation_symbols_map.get(str(operation_name).lower()) # Приводим к нижнему регистру для гибкости

    if not actual_operation_symbol:
        return jsonify({"error": f"Недопустимая или неизвестная операция: '{operation_name}'. Поддерживаемые операции: add, subtract, multiply, divide (и их синонимы/символы)."}), 400

    # Преобразование строковых представлений чисел в float с обработкой ошибок.
    try:
        operand1 = float(num1_str)
        operand2 = float(num2_str)
    except (ValueError, TypeError): # TypeError может быть, если numX_str это None (хотя мы проверили выше)
        return jsonify({"error": "Параметры 'num1' и 'num2' должны быть корректно введенными числами."}), 400

    # Выполнение самой арифметической операции.
    calculation_result = None
    specific_error_message = None

    if actual_operation_symbol == '+':
        calculation_result = operand1 + operand2
    elif actual_operation_symbol == '-':
        calculation_result = operand1 - operand2
    elif actual_operation_symbol == '*':
        calculation_result = operand1 * operand2
    elif actual_operation_symbol == '/':
        if operand2 == 0: # Важнейшая проверка при делении!
            specific_error_message = "Ошибка: деление на ноль невозможно."
        else:
            calculation_result = operand1 / operand2
    
    if specific_error_message:
        # Возвращаем ошибку 400 (Bad Request), так как входные данные привели к ошибке вычисления.
        return jsonify({"error": specific_error_message, "inputs_received": {"num1": operand1, "num2": operand2, "operation_requested": operation_name}}), 400
        
    # Формируем успешный ответ.
    return jsonify({
        "message": "Вычисление успешно выполнено.",
        "input_data_source": request_source_info,
        "operand1": operand1,
        "operand2": operand2,
        "operation_requested_alias": operation_name,
        "operation_performed_symbol": actual_operation_symbol,
        "result": calculation_result
    })

# Сервис 6: Генератор случайных чисел/паролей - API
@app.route('/api/random/number', methods=['GET'])
def random_data_api_get_number():
    """API: Генерирует случайное целое число в заданном диапазоне [min_val, max_val]."""
    # Значения по умолчанию, если параметры не переданы.
    min_val_str = request.args.get('min', '0')
    max_val_str = request.args.get('max', '100')

    try:
        min_value = int(min_val_str)
        max_value = int(max_val_str)
    except ValueError:
        return jsonify({"error": "Параметры 'min' и 'max' должны быть корректными целыми числами."}), 400
    
    if min_value > max_value:
        return jsonify({"error": "Минимальное значение ('min') не может быть больше максимального ('max')."}), 400
    
    # Ограничиваем диапазон для предотвращения чрезмерной нагрузки или нереалистичных запросов.
    # FIXME: Эти "магические числа" (пределы) лучше вынести в конфигурационные константы.
    MAX_RANGE_DIFFERENCE = 1_000_000
    MAX_ABSOLUTE_VALUE = 5_000_000 # Ограничение на сами min/max
    if abs(max_value - min_value) > MAX_RANGE_DIFFERENCE or abs(min_value) > MAX_ABSOLUTE_VALUE or abs(max_value) > MAX_ABSOLUTE_VALUE:
        return jsonify({"error": f"Запрошен слишком большой диапазон чисел. Максимальная разница между min и max: {MAX_RANGE_DIFFERENCE}, максимальное абсолютное значение для min/max: {MAX_ABSOLUTE_VALUE}."}), 400
        
    generated_num = random.randint(min_value, max_value)
    return jsonify({
        "message": "Случайное число успешно сгенерировано.",
        "requested_min_bound": min_value,
        "requested_max_bound": max_value,
        "random_number": generated_num
    })

@app.route('/api/random/password', methods=['GET'])
def random_data_api_get_password():
    """API: Генерирует случайный пароль на основе заданных параметров."""
    try:
        # Более безопасная длина пароля по умолчанию.
        password_length = int(request.args.get('length', '16')) 
    except ValueError:
        return jsonify({"error": "Параметр 'length' (длина пароля) должен быть целым числом."}), 400

    # Разумные ограничения на длину генерируемого пароля.
    MIN_PASS_LENGTH = 6
    MAX_PASS_LENGTH = 128
    if not (MIN_PASS_LENGTH <= password_length <= MAX_PASS_LENGTH):
        return jsonify({"error": f"Длина пароля ('length') должна быть в диапазоне от {MIN_PASS_LENGTH} до {MAX_PASS_LENGTH} символов."}), 400
        
    # Обработка булева параметра для использования спецсимволов.
    # Приводим к нижнему регистру для гибкости ('True', 'true', 'False', 'false').
    use_special_symbols_str = request.args.get('use_symbols', 'true').lower()
    if use_special_symbols_str not in ['true', 'false']:
        return jsonify({"error": "Параметр 'use_symbols' должен иметь значение 'true' или 'false'."}), 400
    include_special_chars = use_special_symbols_str == 'true'

    # Формируем пул символов для генерации пароля.
    character_pool = string.ascii_letters + string.digits # Всегда буквы (верхний/нижний регистр) и цифры
    if include_special_chars:
        # string.punctuation содержит: '!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'
        # Можно определить свой набор "безопасных" спецсимволов, если стандартный не подходит.
        # safe_punctuation = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        character_pool += string.punctuation
        
    # TODO: Улучшить генерацию пароля для гарантии включения различных типов символов
    #       (например, хотя бы одна заглавная, одна строчная, одна цифра, один спецсимвол),
    #       если соответствующие опции выбраны. Текущий метод просто случайно выбирает из пула.
    #       Это потребует более сложной логики, например, сначала выбрать по одному символу
    #       каждого требуемого типа, а затем добирать оставшиеся случайно.

    generated_password_str = ''.join(random.choice(character_pool) for _ in range(password_length))
    
    return jsonify({
        "message": "Пароль успешно сгенерирован.",
        "password": generated_password_str,
        "requested_length": password_length,
        "special_symbols_included": include_special_chars
    })


# --- Сервис 7: Конвертер Единиц Измерения ---

# Данные для конвертации. Ключи - базовые единицы для каждой категории (для упрощения расчетов).
# Значения - коэффициенты относительно базовой единицы.
# Например, для длины базовая единица - метр.
CONVERSION_RATES = {
    "length": {
        "meter": {"name": "Метр (м)", "factor": 1.0},
        "millimeter": {"name": "Миллиметр (мм)", "factor": 0.001},
        "centimeter": {"name": "Сантиметр (см)", "factor": 0.01},
        "decimeter": {"name": "Дециметр (дм)", "factor": 0.1},
        "kilometer": {"name": "Километр (км)", "factor": 1000.0},
        "inch": {"name": "Дюйм (in)", "factor": 0.0254},
        "foot": {"name": "Фут (ft)", "factor": 0.3048},
        "yard": {"name": "Ярд (yd)", "factor": 0.9144},
        "mile": {"name": "Миля (mi)", "factor": 1609.344},
    },
    "volume_metric": { # Используем "кубический метр" как базу
        "cubic_meter": {"name": "Кубический метр (м³)", "factor": 1.0},
        "cubic_centimeter": {"name": "Кубический сантиметр (см³)", "factor": 1e-6}, # 1 (см^3) = 10^-6 м^3
        "milliliter": {"name": "Миллилитр (мл)", "factor": 1e-6}, # 1 мл = 1 см^3
        "liter": {"name": "Литр (л)", "factor": 1e-3},           # 1 л = 1 дм^3 = 1000 см^3 = 0.001 м^3
        "cubic_decimeter": {"name": "Кубический дециметр (дм³)", "factor": 1e-3},
        "cubic_millimeter": {"name": "Кубический миллиметр (мм³)", "factor": 1e-9},
    },
    "data_storage_binary": { # Используем "байт" как базу (двоичная система)
        "byte": {"name": "Байт (B)", "factor": 1.0},
        "bit": {"name": "Бит (bit)", "factor": 1.0 / 8.0},
        "kibibyte": {"name": "Кибибайт (KiB)", "factor": 1024.0}, # 1024 байт
        "mebibyte": {"name": "Мебибайт (MiB)", "factor": 1024.0**2},
        "gibibyte": {"name": "Гибибайт (GiB)", "factor": 1024.0**3},
        "tebibyte": {"name": "Тебибайт (TiB)", "factor": 1024.0**4},
        "pebibyte": {"name": "Пебибайт (PiB)", "factor": 1024.0**5},
    },
    "data_storage_decimal": { # Используем "байт" как базу (десятичная система)
        "byte_decimal": {"name": "Байт (B, дес.)", "factor": 1.0, "base_unit": "byte"}, # Для консистентности ключей
        "kilobyte": {"name": "Килобайт (KB)", "factor": 1000.0}, # 1000 байт
        "megabyte": {"name": "Мегабайт (MB)", "factor": 1000.0**2},
        "gigabyte": {"name": "Гигабайт (GB)", "factor": 1000.0**3},
        "terabyte": {"name": "Терабайт (TB)", "factor": 1000.0**4},
        "petabyte": {"name": "Петабайт (PB)", "factor": 1000.0**5},
    }
    # TODO: Добавить другие категории (вес, температура и т.д.)
}

@app.route('/service/converter')
def service_converter_page():
    """Отображает интерактивную страницу и документацию для сервиса "Конвертер Единиц"."""
    service_page_data = {
        "name": "Конвертер единиц измерения",
        "intro": "Быстро и точно конвертируйте значения между различными единицами длины, объёма и размера данных. Выберите категорию, укажите значение и получите результат!",
        "page_url_name": "service_converter_page",
        "endpoints": [
            {"method": "GET", "path": url_for('converter_api_get_units'), 
             "description": "Получить список доступных категорий и единиц измерения в них."},
            {"method": "GET", "path": f"{url_for('converter_api_convert')}?category=CATEGORY&from_unit=UNIT_A&to_unit=UNIT_B&value=X", 
             "description": "Выполнить конвертацию. Например: ?category=length&from_unit=meter&to_unit=foot&value=10"}
        ]
    }
    return render_template('service_converter.html', service_data=service_page_data, page_title=service_page_data["name"])

@app.route('/api/converter/units', methods=['GET'])
def converter_api_get_units():
    """API: Возвращает доступные категории и единицы для конвертации."""
    # Формируем данные для ответа, чтобы UI было удобно их использовать
    categories_for_response = {}
    for category_key, units_dict in CONVERSION_RATES.items():
        categories_for_response[category_key] = [
            {"id": unit_id, "name": unit_data["name"]} for unit_id, unit_data in units_dict.items()
        ]
    
    category_display_names = {
        "length": "Длина",
        "volume_metric": "Объём (метрическая система)",
        "data_storage_binary": "Размер данных (двоичная)",
        "data_storage_decimal": "Размер данных (десятичная)"
    }
    
    return jsonify({
        "category_names": category_display_names,
        "units_by_category": categories_for_response
        })

@app.route('/api/converter/convert', methods=['GET'])
def converter_api_convert():
    """API: Выполняет конвертацию между единицами."""
    try:
        category = request.args.get('category', type=str)
        from_unit_id = request.args.get('from_unit', type=str)
        to_unit_id = request.args.get('to_unit', type=str)
        value_str = request.args.get('value')

        if not all([category, from_unit_id, to_unit_id, value_str]):
            return jsonify({"error": "Необходимо указать все параметры: category, from_unit, to_unit, value."}), 400

        value = float(value_str) # Преобразуем значение в число

        if category not in CONVERSION_RATES:
            return jsonify({"error": f"Неизвестная категория: {category}."}), 400
        
        category_units = CONVERSION_RATES[category]
        if from_unit_id not in category_units or to_unit_id not in category_units:
            return jsonify({"error": f"Одна из единиц ({from_unit_id} или {to_unit_id}) не найдена в категории {category}."}), 400

        from_unit_data = category_units[from_unit_id]
        to_unit_data = category_units[to_unit_id]

        # Конвертируем значение в базовую единицу категории, затем в целевую единицу
        value_in_base_unit = value * from_unit_data["factor"]
        converted_value = value_in_base_unit / to_unit_data["factor"]
        
        return jsonify({
            "original_value": value,
            "original_unit_id": from_unit_id,
            "original_unit_name": from_unit_data["name"],
            "converted_value": round(converted_value, 6), # Округляем для лучшего вида
            "converted_unit_id": to_unit_id,
            "converted_unit_name": to_unit_data["name"],
            "category": category
        })

    except ValueError:
        return jsonify({"error": "Параметр 'value' должен быть числом."}), 400
    except Exception as e:
        app.logger.error(f"Ошибка конвертации: {e}", exc_info=True)
        return jsonify({"error": "Внутренняя ошибка сервера при конвертации."}), 500


# --- Блок запуска Flask-приложения ---
# Этот код выполняется только тогда, когда скрипт app.py запускается напрямую
# (а не импортируется как модуль в другой скрипт).
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001, debug=True)