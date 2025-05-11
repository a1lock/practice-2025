import os
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import requests
from dotenv import load_dotenv
import uuid # Добавлено для RqUID

load_dotenv() # Загружаем переменные окружения из .env файла

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_default_secret_key') # Используем переменную окружения или дефолтный ключ
socketio = SocketIO(app)

# --- GigaChat API Integration ---
# !! ВАЖНО: Замените значения по умолчанию на ваши реальные данные из .env и документации GigaChat !!
GIGACHAT_CLIENT_ID = os.environ.get("GIGACHAT_CLIENT_ID")
GIGACHAT_CLIENT_SECRET = os.environ.get("GIGACHAT_CLIENT_SECRET")
# URL для получения токена (замените на актуальный из документации)
GIGACHAT_AUTH_URL = os.environ.get("GIGACHAT_AUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
# URL для запросов к чат-модели (замените на актуальный из документации)
GIGACHAT_CHAT_API_URL = os.environ.get("GIGACHAT_CHAT_API_URL", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions")

def get_gigachat_token(client_id, client_secret, auth_url):
    """Получает токен доступа GigaChat."""
    if not client_id or not client_secret:
        print("Ошибка: GigaChat Client ID или Client Secret не найдены в переменных окружения.")
        return None, "Ошибка: Учетные данные GigaChat не настроены."

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': str(uuid.uuid4()), # Уникальный идентификатор запроса
    }
    payload = {
        'scope': 'GIGACHAT_API_PERS', # Или 'GIGACHAT_API_CORP' в зависимости от вашего типа доступа
    }
    # Аутентификация включается через параметр auth в requests
    auth = (client_id, client_secret)

    try:
        response = requests.post(auth_url, headers=headers, data=payload, auth=auth, verify=False, timeout=20) # verify=False часто нужен для GigaChat, но менее безопасен
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get("access_token")
        if not access_token:
             print(f"Ошибка: Не удалось получить access_token из ответа: {token_data}")
             return None, f"Ошибка аутентификации GigaChat: Неожиданный формат ответа {token_data}"
        # expires_at = token_data.get("expires_at") # Можно использовать для кэширования токена
        return access_token, None
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе токена GigaChat: {e}")
        error_message = f"Ошибка аутентификации GigaChat: {e}"
        if response is not None:
             error_message += f" Ответ сервера: {response.text}"
        return None, error_message
    except Exception as e:
        print(f"Непредвиденная ошибка при получении токена GigaChat: {e}")
        return None, "Внутренняя ошибка сервера при аутентификации GigaChat."

def get_gigachat_response(user_input):
    """Запрашивает ответ у GigaChat API."""

    access_token, error = get_gigachat_token(GIGACHAT_CLIENT_ID, GIGACHAT_CLIENT_SECRET, GIGACHAT_AUTH_URL)
    if error:
        return error # Возвращаем ошибку получения токена

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}',
    }
    # !! ВАЖНО: Адаптируйте структуру 'data' под актуальную документацию GigaChat !!
    data = {
        "model": "GigaChat:latest", # Укажите актуальную модель
        "messages": [
            {"role": "system", "content": "Ты - полезный ассистент службы поддержки."},
            {"role": "user", "content": f"Ответь на вопрос клиента кратко, как техподдержка. Вопрос: {user_input}"}
        ],
        "temperature": 0.7, # Пример дополнительных параметров
        # "stream": False # Уточните, поддерживается ли и нужен ли stream
    }

    try:
        response = requests.post(GIGACHAT_CHAT_API_URL, headers=headers, json=data, verify=False, timeout=40)
        response.raise_for_status()
        result = response.json()
        print(f"GigaChat Raw Response: {result}") # Добавлено логирование сырого ответа

        # !! ВАЖНО: Адаптируйте парсинг ответа под актуальную документацию GigaChat !!
        # Примерный парсинг, основанный на стандартной структуре
        try:
            # Попытка извлечь ответ по стандартному пути
            ai_message = result["choices"][0]["message"]["content"]
            if ai_message:
                return ai_message.strip()
            else:
                # Случай, если content пустой или отсутствует внутри message
                print(f"Ошибка: 'content' не найден или пуст в GigaChat response['choices'][0]['message']: {result}")
                return "Ошибка: AI вернул пустой ответ."
        except (KeyError, IndexError, TypeError) as parse_error:
            # Если структура ответа отличается от ожидаемой
            print(f"Ошибка парсинга ответа GigaChat: {parse_error}. Структура ответа: {result}")
            return f"Ошибка: Не удалось разобрать ответ от AI. Проверьте структуру ответа в документации GigaChat. Ответ: {result}"

    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к GigaChat API: {e}")
        error_detail = f"Ошибка: {e}"
        if response is not None:
            try:
                 error_detail += f" Код: {response.status_code}. Ответ: {response.text}"
            except Exception:
                 error_detail += f" Код: {response.status_code}. Не удалось прочитать ответ."

        # Уточнение типа ошибки для пользователя
        if isinstance(e, requests.exceptions.Timeout):
            return "Ошибка: Время ожидания ответа от AI сервиса истекло."
        elif isinstance(e, requests.exceptions.ConnectionError):
            return "Ошибка: Не удалось подключиться к AI сервису."
        elif isinstance(e, requests.exceptions.HTTPError):
             return f"Ошибка: AI сервис вернул ошибку HTTP {response.status_code}. Проверьте API ключ и параметры запроса. {error_detail}"
        else:
             return f"Ошибка: Произошла проблема при обращении к AI сервису. {error_detail}"
    except Exception as e:
        print(f"Непредвиденная ошибка при обработке ответа GigaChat: {e}")
        return "Ошибка: Произошла внутренняя ошибка сервера при обработке запроса к AI."


# --- Flask Routes ---
@app.route('/')
def index():
    """Отображает главную страницу чата."""
    return render_template('index.html')

# --- SocketIO Event Handlers ---
@socketio.on('connect')
def handle_connect():
    """Обработчик подключения нового клиента."""
    print('Client connected:', request.sid)
    emit('chat_message', {'user': 'System', 'text': 'Добро пожаловать в чат!'}) # Приветственное сообщение

@socketio.on('disconnect')
def handle_disconnect():
    """Обработчик отключения клиента."""
    print('Client disconnected:', request.sid)

@socketio.on('user_message')
def handle_user_message(message):
    """Обрабатывает сообщение от пользователя и запрашивает ответ у ИИ."""
    user_input = message.get('text', '').strip()
    print(f"Received message from {request.sid}: {user_input}")

    if not user_input:
        return # Игнорируем пустые сообщения

    # Отправляем сообщение пользователя в чат для отображения
    emit('chat_message', {'user': 'Вы', 'text': user_input}, room=request.sid)

    # Получаем ответ от ИИ (теперь используем GigaChat)
    ai_response = get_gigachat_response(user_input)

    # Отправляем ответ ИИ обратно клиенту
    emit('chat_message', {'user': 'AI Ассистент', 'text': ai_response}, room=request.sid)


# --- Run Application ---
if __name__ == '__main__':
    print("Starting server...")
    # Используем localhost и порт 5000 по умолчанию
    # Для доступа из локальной сети можно использовать host='0.0.0.0'
    # debug=True включает режим отладки Flask (автоперезагрузка при изменениях)
    # allow_unsafe_werkzeug=True может потребоваться для некоторых версий Flask/SocketIO в режиме отладки
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True, host='127.0.0.1', port=5000) 