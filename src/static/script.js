// Устанавливаем соединение с Socket.IO сервером
// Используем `io()` без аргументов, так как сервер на том же хосте и порте
const socket = io();

// Получаем ссылки на элементы DOM
const chatBox = document.getElementById('chat-box');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');

// Функция для добавления сообщения в чат
function addMessage(sender, text, type) {
    const messageElement = document.createElement('div');
    messageElement.classList.add('message');
    messageElement.classList.add(type); // Добавляем класс 'user' или 'ai'

    const senderElement = document.createElement('span');
    senderElement.classList.add('sender');
    senderElement.textContent = sender + ':';

    const textElement = document.createElement('span');
    textElement.textContent = text;

    messageElement.appendChild(senderElement);
    messageElement.appendChild(textElement);

    chatBox.appendChild(messageElement);

    // Автоматическая прокрутка вниз
    chatBox.scrollTop = chatBox.scrollHeight;
}

// Функция отправки сообщения
function sendMessage() {
    const messageText = messageInput.value.trim();
    if (messageText !== '') {
        console.log("Sending message:", messageText); // Отладка
        // Отправляем сообщение на сервер через событие 'user_message'
        socket.emit('user_message', { text: messageText });
        messageInput.value = ''; // Очищаем поле ввода
    } else {
        console.log("Cannot send empty message"); // Отладка
    }
}

// Обработчик нажатия кнопки "Отправить"
sendButton.addEventListener('click', sendMessage);

// Обработчик нажатия Enter в поле ввода
messageInput.addEventListener('keypress', function(event) {
    if (event.key === 'Enter') {
        event.preventDefault(); // Предотвращаем стандартное поведение Enter (перенос строки)
        sendMessage();
    }
});

// Обработчик получения сообщения от сервера
socket.on('chat_message', function(data) {
    console.log("Received message:", data); // Отладка
    const messageType = data.user === 'Вы' ? 'user' : (data.user === 'System' ? 'system' : 'ai');
    addMessage(data.user, data.text, messageType);
});

// Обработчик события подключения
socket.on('connect', () => {
    console.log('Connected to server with SID:', socket.id);
});

// Обработчик события отключения
socket.on('disconnect', (reason) => {
    console.log('Disconnected from server:', reason);
    addMessage('System', 'Потеряно соединение с сервером.', 'system');
});

// Обработчик ошибок подключения
socket.on("connect_error", (err) => {
    console.error("Connection error:", err);
    addMessage('System', `Ошибка подключения: ${err.message}`, 'system');
}); 