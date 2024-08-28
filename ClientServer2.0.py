import base64
import os
import socketio
import requests
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QTextEdit, QListWidget, QMessageBox, QDialog, QListWidgetItem, QFileDialog
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor, QColor, QFont, QBrush

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

@sio.event
def private_message(data):
    """Обработчик для получения личных сообщений."""
    sender = data.get('from')
    recipient = data.get('to')
    message = data.get('text')

    if recipient == current_username:
        # Обработка отображения сообщения в приватном чате
        if sender in private_chat_windows:
            private_chat_listbox = private_chat_windows[sender]['listbox']
            private_chat_listbox.addItem(f"{sender}: {message}")

            # Обновляем ползунок прокрутки
            scrollbar = private_chat_listbox.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        else:
            # Если чат с этим пользователем не открыт, ничего не делаем
            pass

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
            private_chat_listbox = private_chat_windows[username]['listbox']
            for msg in messages:
                private_chat_listbox.addItem(f"{msg.get('sender', 'Unknown')}: {msg.get('text', '')}")
            
            # Обновляем ползунок прокрутки
            scrollbar = private_chat_listbox.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
    else:
        print(f"Неизвестный тип чата: {chat_type}")

def start_private_chat(username):
    """Открытие окна для личного чата с пользователем."""
    global private_chat_windows

    if username in private_chat_windows:
        private_chat_windows[username]['window'].show()
    else:
        private_chat_window = QMainWindow()
        private_chat_window.setWindowTitle(f"Чат с {username}")
        private_chat_window.setStyleSheet(f"background-color: {BG_COLOR};")

        layout = QVBoxLayout()

        private_chat_listbox = QListWidget()
        private_chat_listbox.setStyleSheet(f"""
            background-color: {ENTRY_BG_COLOR};
            border-radius: 10px;
            padding: 10px;
            color: {TEXT_COLOR};
        """)
        private_chat_listbox.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        private_chat_listbox.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        layout.addWidget(private_chat_listbox)

        private_message_entry = QTextEdit()
        private_message_entry.setStyleSheet(f"""
            background-color: {ENTRY_BG_COLOR};
            border-radius: 10px;
            padding: 10px;
            color: {TEXT_COLOR};
            border: 2px solid {BUTTON_COLOR}; /* Основная рамка */
        """)
        layout.addWidget(private_message_entry)

        button_layout = QHBoxLayout()
        send_button = QPushButton("Отправить")
        send_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
        send_button.clicked.connect(lambda: send_private_message(username))
        button_layout.addWidget(send_button)

        attach_button = QPushButton("Прикрепить файл")
        attach_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
        attach_button.clicked.connect(lambda: attach_file(username))
        button_layout.addWidget(attach_button)

        layout.addLayout(button_layout)

        chat_container = QWidget()
        chat_container.setLayout(layout)
        
        private_chat_window.setCentralWidget(chat_container)
        private_chat_window.show()

        private_chat_windows[username] = {
            'window': private_chat_window,
            'listbox': private_chat_listbox,
            'entry': private_message_entry
        }

        sio.emit('request_chat_history', {'type': 'private', 'username': username})

        if username in unread_counts:
            unread_counts[username] = 0
            update_user_listbox()

def send_private_message(username):
    """Отправка личного сообщения."""
    if username not in private_chat_windows:
        QMessageBox.warning(main_window, "Ошибка", f"Чат с {username} не открыт.")
        return

    message = private_chat_windows[username]['entry'].toPlainText()
    if not message:
        return

    sio.emit('private_message', {'to': username, 'text': message, 'from': current_username})

    private_chat_listbox = private_chat_windows[username]['listbox']
    private_chat_listbox.addItem(f"{current_username}: {message}")

    # Обновляем ползунок прокрутки
    scrollbar = private_chat_listbox.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())

    private_chat_windows[username]['entry'].clear()

    if username in unread_counts:
        unread_counts[username] = unread_counts.get(username, 0)
        update_user_listbox()

def attach_file(username):
    """Выбор и отправка файла в личном чате."""
    if username not in private_chat_windows:
        QMessageBox.warning(main_window, "Ошибка", f"Чат с {username} не открыт.")
        return

    file_path, _ = QFileDialog.getOpenFileName(main_window, "Выберите файл для отправки")
    if file_path:
        try:
            with open(file_path, 'rb') as file:
                file_data = file.read()
                encoded_file = base64.b64encode(file_data).decode('utf-8')  # Кодируем файл в Base64

                print(f"Отправка файла {os.path.basename(file_path)} размером {len(file_data)} байт")  # Лог
                
                sio.emit('upload_file', {  # Изменить на правильное событие
                    'to': username,
                    'from': current_username,
                    'file': {
                        'name': os.path.basename(file_path),
                        'content': encoded_file
                    }
                })

                private_chat_listbox = private_chat_windows[username]['listbox']
                private_chat_listbox.addItem(f"{current_username}: Файл: {os.path.basename(file_path)}")

                # Обновляем ползунок прокрутки
                scrollbar = private_chat_listbox.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())

        except Exception as e:
            QMessageBox.critical(main_window, "Ошибка", f"Не удалось отправить файл: {str(e)}")
@sio.event
def file_message(data):
    """Обработчик для получения файлов."""
    sender = data.get('from')
    recipient = data.get('to')
    file_info = data.get('file', {})
    file_name = file_info.get('name')
    file_content = file_info.get('content')

    if recipient == current_username:
        if file_name and file_content:
            # Декодирование файла
            file_data = base64.b64decode(file_content)
            
            # Создание временного файла для скачивания
            temp_file_path = os.path.join(os.getenv('TEMP', '.'), file_name)
            with open(temp_file_path, 'wb') as file:
                file.write(file_data)

            # Добавление ссылки на файл в чат
            file_link = f'<a href="file:///{temp_file_path}">Скачать {file_name}</a>'
            chat_box.append(f"{sender}: {file_link}")

            # Обновляем ползунок прокрутки
            scrollbar = chat_box.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        else:
            QMessageBox.warning(main_window, "Ошибка", "Ошибка получения файла.")


def send_message():
    """Отправка сообщения в общий чат."""
    global message_entry

    message = message_entry.toPlainText()
    if not message:
        return

    sio.emit('global_message', {'text': message, 'sender': current_username})

    chat_box.append(f"{current_username}: {message}")

    # Обновляем ползунок прокрутки
    scrollbar = chat_box.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())

    message_entry.clear()

def update_user_listbox():
    """Обновление списка пользователей с учетом непрочитанных сообщений."""
    global user_listbox, all_users, unread_counts, private_chat_windows

    user_listbox.clear()
    for user in all_users:
        display_name = user
        if user in unread_counts and unread_counts[user] > 0 and user not in private_chat_windows:
            display_name += " <b style='color: red;'>!</b>"
        item = QListWidgetItem(display_name)
        item.setForeground(QBrush(QColor(USER_COLOR)))  # Устанавливаем цвет текста
        user_listbox.addItem(item)

def setup_main_window():
    """Настройка основного окна приложения."""
    global main_window, chat_box, message_entry, user_listbox

    main_window = QMainWindow()
    main_window.setWindowTitle("Чат")
    main_window.setStyleSheet(f"background-color: {BG_COLOR};")

    central_widget = QWidget()
    main_window.setCentralWidget(central_widget)
    layout = QHBoxLayout(central_widget)  # Изменен макет на горизонтальный

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
    user_frame.setFixedWidth(200)  # Устанавливаем фиксированную ширину для списка пользователей
    layout.addWidget(user_frame)

    chat_frame = QWidget()
    chat_layout = QVBoxLayout(chat_frame)

    # Добавляем QTextEdit с ползунком
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
    
    # Основной стиль для поля ввода сообщений
    message_entry = QTextEdit()
    message_entry.setStyleSheet(f"""
        background-color: {ENTRY_BG_COLOR};
        border-radius: 10px;
        padding: 10px;
        color: {TEXT_COLOR};
        border: 2px solid {BUTTON_COLOR}; /* Основная рамка */
        border-top: 3px solid {BUTTON_HOVER_COLOR}; /* Дополнительная рамка сверху для выделения */
    """)
    input_layout.addWidget(message_entry)
    
    send_button = QPushButton("Отправить")
    send_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
    send_button.clicked.connect(send_message)
    input_layout.addWidget(send_button)
    
    chat_layout.addWidget(input_frame)  # Перемещаем ввод сообщений в chat_layout
    layout.addWidget(chat_frame)  # Добавляем chat_frame в основной layout

    user_listbox.itemDoubleClicked.connect(lambda item: start_private_chat(item.text().split(' ')[0]))

    connect_socket()

    if not history_loaded:
        sio.emit('request_chat_history', {'type': 'global'})

    main_window.show()

if __name__ == "__main__":
    app = QApplication([])

    login_window = QMainWindow()
    login_window.setWindowTitle("Вход")
    login_window.setStyleSheet(f"background-color: {BG_COLOR};")

    central_widget = QWidget()
    login_window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)

    login_label = QLabel("Логин", login_window)
    login_label.setStyleSheet(f"color: {HEADING_COLOR}; font-weight: bold;")
    layout.addWidget(login_label)

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
    login_button = QPushButton("Войти")
    login_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
    login_button.clicked.connect(login)
    button_layout.addWidget(login_button)

    register_button = QPushButton("Регистрация")
    register_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
    register_button.clicked.connect(open_registration_window)
    button_layout.addWidget(register_button)

    layout.addLayout(button_layout)
    login_window.show()

    app.exec()
