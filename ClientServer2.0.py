import os
import socketio
import requests
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QTextEdit, QListWidget, QMessageBox, QDialog, QListWidgetItem, QFileDialog
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QBrush
import base64

HOST = 'http://10.1.3.187:12345'
sio = socketio.Client()
token = None

login_window = None
reg_window = None
main_window = None
current_username = None
user_listbox = None
chat_box = None
message_entry = None
all_users = []  # Список всех зарегистрированных пользователей
private_chat_windows = {}  # Словарь для хранения ссылок на окна приватных чатов
unread_counts = {}  # Словарь для хранения количества непрочитанных сообщений
history_loaded = False  # Флаг для отслеживания загрузки истории сообщений

# Цвета и шрифты
BG_COLOR = "#1e1e1e"        # Фоновый цвет
TEXT_COLOR = "#e0e0e0"      # Цвет текста
BUTTON_COLOR = "#0077ff"    # Цвет кнопок
BUTTON_HOVER_COLOR = "#0059b3"  # Цвет кнопок при наведении
ENTRY_BG_COLOR = "#2b2b2b"  # Цвет полей ввода
HEADING_COLOR = "#c0c0c0"   # Цвет заголовков
USER_COLOR = "#0077ff"      # Цвет пользователей

def register():
    """Обработчик регистрации нового пользователя."""
    username = reg_username_entry.text()
    password = reg_password_entry.text()

    if not username or not password:
        QMessageBox.critical(reg_window, "Ошибка", "Введите логин и пароль!")
        return

    try:
        response = requests.post(f"{HOST}/register", json={'username': username, 'password': password})
        if response.status_code == 201:
            QMessageBox.information(reg_window, "Успех", "Регистрация прошла успешно!")
            reg_window.accept()
        else:
            QMessageBox.critical(reg_window, "Ошибка", response.json().get('message', 'Неизвестная ошибка'))
    except Exception as e:
        QMessageBox.critical(reg_window, "Ошибка", str(e))

def send_file(recipient_username):
    """Открывает диалог для выбора файла и отправляет его на сервер."""
    file_path, _ = QFileDialog.getOpenFileName(main_window, "Выберите файл")
    if file_path:
        file_name = os.path.basename(file_path)
        with open(file_path, 'rb') as file:
            file_data = file.read()
            # Отправляем файл на сервер
            sio.emit('file_upload', {'file_name': file_name, 'file_data': file_data, 'to': recipient_username})
        chat_box.append(f"Вы отправили файл: {file_name}")

def open_registration_window():
    """Открывает окно регистрации."""
    global reg_window, reg_username_entry, reg_password_entry

    reg_window = QDialog(login_window)
    reg_window.setWindowTitle("Регистрация")
    reg_window.setStyleSheet(f"background-color: {BG_COLOR};")

    layout = QVBoxLayout()

    username_label = QLabel("Логин", reg_window)
    username_label.setStyleSheet(f"color: {HEADING_COLOR}; font-weight: bold;")
    layout.addWidget(username_label)

    reg_username_entry = QLineEdit(reg_window)
    reg_username_entry.setStyleSheet(f"background-color: {ENTRY_BG_COLOR}; border-radius: 10px; padding: 10px; color: {TEXT_COLOR};")
    layout.addWidget(reg_username_entry)

    password_label = QLabel("Пароль", reg_window)
    password_label.setStyleSheet(f"color: {HEADING_COLOR}; font-weight: bold;")
    layout.addWidget(password_label)

    reg_password_entry = QLineEdit(reg_window)
    reg_password_entry.setStyleSheet(f"background-color: {ENTRY_BG_COLOR}; border-radius: 10px; padding: 10px; color: {TEXT_COLOR};")
    reg_password_entry.setEchoMode(QLineEdit.Password)
    layout.addWidget(reg_password_entry)

    button_layout = QHBoxLayout()
    register_button = QPushButton("Зарегистрироваться", reg_window)
    register_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
    register_button.clicked.connect(register)
    button_layout.addWidget(register_button)

    cancel_button = QPushButton("Отмена", reg_window)
    cancel_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
    cancel_button.clicked.connect(reg_window.reject)
    button_layout.addWidget(cancel_button)

    layout.addLayout(button_layout)
    reg_window.setLayout(layout)
    reg_window.exec()

def login():
    """Обработчик входа пользователя."""
    global login_window, username_entry, password_entry, token, current_username

    username = username_entry.text()
    password = password_entry.text()

    if not username or not password:
        QMessageBox.critical(login_window, "Ошибка", "Введите логин и пароль!")
        return

    try:
        response = requests.post(f"{HOST}/login", json={'username': username, 'password': password})
        if response.status_code == 200:
            token = response.json().get('token')
            current_username = username  # Сохраняем текущего пользователя
            login_window.close()
            setup_main_window()
        else:
            QMessageBox.critical(login_window, "Ошибка", response.json().get('message', 'Неизвестная ошибка'))
    except Exception as e:
        QMessageBox.critical(login_window, "Ошибка", str(e))

def connect_socket():
    """Подключение к серверу через WebSocket."""
    global token

    sio.connect(HOST, headers={'Authorization': f'Bearer {token}'})

@sio.event
def connect():
    print("Соединение установлено")

@sio.event
def disconnect():
    print("Отключение")

@sio.event
def all_users(users):
    """Обработчик для получения списка всех пользователей."""
    global all_users
    print(f"Received all users: {users}")
    all_users = users
    update_user_listbox()

@sio.event
def global_message(data):
    """Обработчик для получения сообщений из общего чата."""
    if 'text' in data and 'sender' in data:
        text = data['text']
        sender = data['sender']
        chat_box.append(f"{sender}: {text}")

        # Обновляем ползунок прокрутки
        scrollbar = chat_box.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

def save_file(file_name, file_data):
    """Сохранение полученного файла на диск."""
    file_path = QFileDialog.getSaveFileName(main_window, "Сохранить файл", file_name)[0]
    if file_path:
        try:
            with open(file_path, 'wb') as file:
                file.write(file_data)
            QMessageBox.information(main_window, "Успех", f"Файл сохранен как {file_path}")
        except Exception as e:
            QMessageBox.critical(main_window, "Ошибка", f"Не удалось сохранить файл: {str(e)}")

@sio.event
def file_received(data):
    """Обработчик для получения файлов."""
    print("Received data:", data)  # Вывод данных для проверки
    from_user = data.get('from')
    file_name = data.get('file_name')
    file_data = data.get('file_data')
    
    if file_name:
        save_file(file_name, file_data)
        chat_box.append(f"{from_user}: Отправлен файл: {file_name}")
    else:
        chat_box.append(f"{from_user}: Получен файл, но имя файла не указано.")

@sio.event
def private_message(data):
    """Обработчик для получения личных сообщений."""
    sender = data.get('from')
    recipient = data.get('to')
    message = data.get('text')
    file_name = data.get('file_name')
    file_data = data.get('file_data')

    print(f"Получено сообщение от {sender} для {recipient}")
    if file_name:
        print(f"Получен файл: {file_name}, размер: {len(file_data)} байт")
    if message:
        print(f"Сообщение: {message}")

    if recipient == current_username:
        if recipient in private_chat_windows:
            private_chat_text_edit = private_chat_windows[recipient]['text_edit']
            
            if file_name and file_data:
                # Обрабатываем файл: сохраняем его и добавляем сообщение
                save_file(file_name, file_data)
                private_chat_text_edit.append(f"{sender}: Отправлен файл: {file_name}")
            else:
                private_chat_text_edit.append(f"{sender}: {message}")

            # Обновляем ползунок прокрутки
            scrollbar = private_chat_text_edit.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        else:
            print(f"Чат с пользователем {recipient} не открыт")

        if sender != current_username:
            unread_counts[sender] = unread_counts.get(sender, 0) + 1
            QTimer.singleShot(0, update_user_listbox)

@sio.event
def chat_history(data):
    """Обработчик для получения истории сообщений."""
    global history_loaded
    messages = data.get('messages', [])
    chat_type = data.get('type', 'unknown')
    username = data.get('username', '')

    print(f"chat_history: {chat_type}, {username}")
    print(f"private_chat_windows: {private_chat_windows}")

    if chat_type == 'global':
        if not history_loaded:
            for msg in messages:
                chat_box.append(f"{msg.get('sender', 'Unknown')}: {msg.get('text', '')}")
            
            # Обновляем ползунок прокрутки
            scrollbar = chat_box.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            history_loaded = True
    elif chat_type == 'private':
        if username in private_chat_windows:
            text_edit = private_chat_windows[username]['text_edit']
            for msg in messages:
                text_edit.append(f"{msg.get('sender', 'Unknown')}: {msg.get('text', '')}")

def send_message():
    """Отправка сообщения в общий чат или личный чат."""
    global current_username

    text = message_entry.toPlainText().strip()
    if text:
        message_entry.clear()
        sio.emit('global_message', {'text': text, 'sender': current_username})
        chat_box.append(f"{current_username}: {text}")

        # Обновляем ползунок прокрутки
        scrollbar = chat_box.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

def update_user_listbox():
    """Обновление списка пользователей."""
    global user_listbox, all_users, unread_counts

    user_listbox.clear()
    for user in all_users:
        if user == current_username:
            continue
        item_text = f"{user} ({unread_counts.get(user, 0)} нов.)"
        item = QListWidgetItem(item_text)
        item.setForeground(QBrush(QColor(USER_COLOR)))
        user_listbox.addItem(item)

def start_private_chat(username):
    """Открытие личного чата с пользователем."""
    global private_chat_windows

    if username in private_chat_windows:
        private_chat_windows[username]['window'].raise_()
        private_chat_windows[username]['window'].activateWindow()
        return

    private_chat_window = QWidget()
    private_chat_window.setWindowTitle(f"Личный чат с {username}")
    private_chat_window.setStyleSheet(f"background-color: {BG_COLOR};")

    layout = QVBoxLayout(private_chat_window)

    text_edit = QTextEdit()
    text_edit.setReadOnly(True)
    text_edit.setStyleSheet(f"""
        background-color: {ENTRY_BG_COLOR};
        border-radius: 10px;
        padding: 10px;
        color: {TEXT_COLOR};
        border: 2px solid {BUTTON_COLOR};
    """)
    layout.addWidget(text_edit)

    input_frame = QWidget()
    input_layout = QHBoxLayout(input_frame)
    
    private_message_entry = QTextEdit()
    private_message_entry.setStyleSheet(f"""
        background-color: {ENTRY_BG_COLOR};
        border-radius: 10px;
        padding: 10px;
        color: {TEXT_COLOR};
        border: 2px solid {BUTTON_COLOR};
        border-top: 3px solid {BUTTON_HOVER_COLOR};
    """)
    input_layout.addWidget(private_message_entry)
    
    send_button = QPushButton("Отправить")
    send_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
    send_button.clicked.connect(lambda: send_private_message(username, private_message_entry))
    input_layout.addWidget(send_button)
    
    layout.addWidget(input_frame)

    private_chat_windows[username] = {
        'window': private_chat_window,
        'text_edit': text_edit,
        'message_entry': private_message_entry
    }

    private_chat_window.show()

    # Запрашиваем историю чата
    sio.emit('request_chat_history', {'type': 'private', 'username': username})

def send_private_message(username, message_entry):
    """Отправка личного сообщения."""
    text = message_entry.toPlainText().strip()
    if text:
        message_entry.clear()
        sio.emit('private_message', {'to': username, 'text': text, 'from': current_username})
        private_chat_windows[username]['text_edit'].append(f"{current_username}: {text}")

        # Обновляем ползунок прокрутки
        scrollbar = private_chat_windows[username]['text_edit'].verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

def setup_main_window():
    """Настройка основного окна приложения."""
    global main_window, chat_box, message_entry, user_listbox

    main_window = QMainWindow()
    main_window.setWindowTitle("Чат")
    main_window.setStyleSheet(f"background-color: {BG_COLOR};")

    central_widget = QWidget()
    main_window.setCentralWidget(central_widget)
    layout = QHBoxLayout(central_widget)

    user_frame = QWidget()
    user_layout = QVBoxLayout(user_frame)
    user_label = QLabel("Пользователи", main_window)
    user_label.setStyleSheet(f"color: {HEADING_COLOR}; font-weight: bold;")
    user_layout.addWidget(user_label)
    user_listbox = QListWidget()
    user_listbox.setStyleSheet(f"background-color: {ENTRY_BG_COLOR}; border-radius: 10px; padding: 10px; color: {TEXT_COLOR};")
    user_listbox.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    user_listbox.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    user_layout.addWidget(user_listbox)
    user_frame.setFixedWidth(200)
    layout.addWidget(user_frame)

    chat_frame = QWidget()
    chat_layout = QVBoxLayout(chat_frame)

    chat_box = QTextEdit()
    chat_box.setReadOnly(True)
    chat_box.setStyleSheet(f"""
        background-color: {ENTRY_BG_COLOR};
        border-radius: 10px;
        padding: 10px;
        color: {TEXT_COLOR};
        border: 2px solid {BUTTON_COLOR};
    """)
    chat_box.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    chat_box.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    chat_layout.addWidget(chat_box)

    input_frame = QWidget()
    input_layout = QHBoxLayout(input_frame)
    
    message_entry = QTextEdit()
    message_entry.setStyleSheet(f"""
        background-color: {ENTRY_BG_COLOR};
        border-radius: 10px;
        padding: 10px;
        color: {TEXT_COLOR};
        border: 2px solid {BUTTON_COLOR};
        border-top: 3px solid {BUTTON_HOVER_COLOR};
    """)
    input_layout.addWidget(message_entry)
    
    send_button = QPushButton("Отправить")
    send_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
    send_button.clicked.connect(send_message)
    input_layout.addWidget(send_button)
    
    send_file_button = QPushButton("Отправить файл")
    send_file_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
    send_file_button.clicked.connect(lambda: send_file(current_username))
    input_layout.addWidget(send_file_button)
    
    chat_layout.addWidget(input_frame)
    layout.addWidget(chat_frame)

    user_listbox.itemDoubleClicked.connect(lambda item: start_private_chat(item.text().split(' ')[0]))

    connect_socket()

    if not history_loaded:
        sio.emit('request_chat_history', {'type': 'global'})

    main_window.show()


def open_login_window():
    """Открытие окна входа."""
    global login_window, username_entry, password_entry

    login_window = QDialog()
    login_window.setWindowTitle("Вход")
    login_window.setStyleSheet(f"background-color: {BG_COLOR};")

    layout = QVBoxLayout()

    username_label = QLabel("Логин", login_window)
    username_label.setStyleSheet(f"color: {HEADING_COLOR}; font-weight: bold;")
    layout.addWidget(username_label)

    username_entry = QLineEdit(login_window)
    username_entry.setStyleSheet(f"background-color: {ENTRY_BG_COLOR}; border-radius: 10px; padding: 10px; color: {TEXT_COLOR};")
    layout.addWidget(username_entry)

    password_label = QLabel("Пароль", login_window)
    password_label.setStyleSheet(f"color: {HEADING_COLOR}; font-weight: bold;")
    layout.addWidget(password_label)

    password_entry = QLineEdit(login_window)
    password_entry.setStyleSheet(f"background-color: {ENTRY_BG_COLOR}; border-radius: 10px; padding: 10px; color: {TEXT_COLOR};")
    password_entry.setEchoMode(QLineEdit.Password)
    layout.addWidget(password_entry)

    button_layout = QHBoxLayout()
    login_button = QPushButton("Войти", login_window)
    login_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
    login_button.clicked.connect(login)
    button_layout.addWidget(login_button)

    register_button = QPushButton("Регистрация", login_window)
    register_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
    register_button.clicked.connect(open_registration_window)
    button_layout.addWidget(register_button)

    layout.addLayout(button_layout)
    login_window.setLayout(layout)
    login_window.exec()

if __name__ == "__main__":
    app = QApplication([])

    open_login_window()

    app.exec()
