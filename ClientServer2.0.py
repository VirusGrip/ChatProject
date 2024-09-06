import os
from flask import json
import socketio
import requests
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QTextEdit, QListWidget, QMessageBox, QDialog, QListWidgetItem, QFileDialog,  QTextBrowser, QGridLayout, QToolButton, QScrollArea, QMenu
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QBrush, QTextCursor
import webbrowser
import urllib.parse
from functools import partial


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
all_user_data = []   # Список всех зарегистрированных пользователей
private_chat_windows = {}  # Словарь для хранения ссылок на окна приватных чатов
history_loaded = False  # Флаг для отслеживания загрузки истории сообщений
unread_messages = {} 
chat_windows_state = {}  # Новый словарь для отслеживания состояния окон чатов
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
    last_name = reg_last_name_entry.text()
    first_name = reg_first_name_entry.text()
    middle_name = reg_middle_name_entry.text()
    birth_date = reg_birth_date_entry.text()
    work_email = reg_work_email_entry.text()
    personal_email = reg_personal_email_entry.text()
    phone_number = reg_phone_number_entry.text()
    password = reg_password_entry.text()

    if not (last_name and first_name and middle_name and birth_date and password):
        QMessageBox.critical(reg_window, "Ошибка", "Пожалуйста, заполните все обязательные поля!")
        return

    # Генерация логина
    username = f"{last_name}{first_name[0]}{middle_name[0]}"

    user_data = {
        'username': username,
        'password': password,
        'last_name': last_name,
        'first_name': first_name,
        'middle_name': middle_name,
        'birth_date': birth_date,
        'work_email': work_email,
        'personal_email': personal_email,
        'phone_number': phone_number
    }

    try:
        response = requests.post(f"{HOST}/register", json=user_data)
        if response.status_code == 201:
            QMessageBox.information(reg_window, "Успех", "Регистрация прошла успешно!")
            reg_window.accept()
        else:
            QMessageBox.critical(reg_window, "Ошибка", response.json().get('message', 'Неизвестная ошибка'))
    except Exception as e:
        QMessageBox.critical(reg_window, "Ошибка", str(e))


def create_file_link(file_name):
    """Создает ссылку для файла, корректно кодируя имя файла."""
    return f"{HOST}/uploads/{urllib.parse.quote(file_name)}"

def open_emoji_picker(target_widget=None):
    print(f"Тип виджета: {type(target_widget)}")  # Добавьте эту строку для отладки
    if not isinstance(target_widget, (QTextEdit, QTextBrowser)):
        print("Ошибка: target_widget не является QTextEdit или QTextBrowser")
        return
    emoji_window = QDialog(main_window)
    emoji_window.setWindowTitle("Выбор эмодзи")

    # Устанавливаем светло-голубой фон для окна и фиксированный размер
    emoji_window.setStyleSheet("background-color: #ADD8E6;")  # Светло-голубой цвет
    emoji_window.setFixedSize(400, 300)  # Устанавливаем размер окна

    scroll_area = QScrollArea(emoji_window)
    scroll_area.setWidgetResizable(True)

    emoji_container = QWidget()
    layout = QGridLayout(emoji_container)

    # Ограниченный набор эмодзи (как в ВКонтакте)
    standard_emojis = [
        "😀", "😁", "😂", "🤣", "😃", "😄", "😅", "😆", "😉", "😊",
        "😋", "😎", "😍", "😘", "😗", "😙", "😚", "🙂", "🤗", "🤔",
        "😐", "😑", "😶", "🙄", "😏", "😣", "😥", "😮", "🤐", "👽",
        "😯", "😪", "😫", "😴", "😌", "😛", "😜", "😝", "🤤", "😒",
        "😓", "😔", "😕", "🙃", "🤑", "😲", "☹️", "🙁", "😖", "😞",
        "😟", "😤", "😢", "😭", "😦", "😧", "😨", "😩", "😰", "😱",
        "😳", "😵", "😡", "😠", "😷", "🤒", "🤕", "🤢", "👻", "💀",
        "🤧", "😇", "🤠", "🤡", "🤥", "🤓", "😈", "👿", "👹", "👺",  
        "🤖", "💩", "😺", "😸", "😹", "😻", "😼", "😽", "🙀", "😿",
        "😾", "🙈", "🙉", "🙊", "🐵", "🐶", "🐱", "🐭", "🐹", "🐰",
        "🦊", "🐻", "🐼", "🐨", "🐯", "🦁", "🐮", "🐷", "🐽", "🐸",
        "🐵", "🐔", "🐧", "🐦", "🐤", "🐣", "🐥", "🦆", "🦅", "🦉"
    ]

    row, col = 0, 0
    for symbol in standard_emojis:
        button = QToolButton()
        button.setText(symbol)

        # Уменьшаем расстояние между кнопками
        button.setStyleSheet("margin: 2px; padding: 5px; font-size: 16px;")  # Уменьшенные отступы и шрифт

        # Используем partial для передачи правильных аргументов
        button.clicked.connect(partial(insert_emoji, symbol, target_widget))
        layout.addWidget(button, row, col)
        col += 1
        if col > 4:  # Ограничиваем количество кнопок в строке
            col = 0
            row += 1

    emoji_container.setLayout(layout)
    scroll_area.setWidget(emoji_container)

    main_layout = QVBoxLayout(emoji_window)
    main_layout.addWidget(scroll_area)
    emoji_window.setLayout(main_layout)

    emoji_window.exec()

def insert_emoji(symbol, target_widget):
    """Вставляет выбранный эмодзи в текстовое поле."""
    if isinstance(target_widget, QTextEdit) or isinstance(target_widget, QTextBrowser):
        current_cursor = target_widget.textCursor()
        current_cursor.insertText(symbol)
    else:
        print("Ошибка: target_widget не является QTextEdit или QTextBrowser")

def send_private_file(recipient_username):
    """Открывает диалог для выбора файла и отправляет его в приватный чат."""
    file_path, _ = QFileDialog.getOpenFileName(main_window, "Выберите файл")
    if file_path:
        file_name = os.path.basename(file_path)
        with open(file_path, 'rb') as file:
            file_data = file.read()
            # Отправляем файл на сервер через отдельное событие
            sio.emit('private_file_upload', {
                'to': recipient_username, 
                'file_name': file_name, 
                'file_data': file_data, 
                'from': current_username
            })

        # Отображаем сообщение о загруженном файле в окне приватного чата
        file_url = create_file_link(file_name)
        private_chat_windows[recipient_username]['text_edit'].append(
            f"Вы отправили файл: <a href='{file_url}' style='color: {USER_COLOR}; text-decoration: none;'>{file_name}</a>"
        )
        private_chat_windows[recipient_username]['text_edit'].append("")  # Пустая строка для форматирования


def create_download_button(file_name, file_data):
    """Создает кнопку для загрузки файла и связывает ее с функцией обработки."""
    button = QPushButton(f"Скачать {file_name}")
    button.clicked.connect(lambda: save_file(file_name, file_data))
    return button

def send_file(recipient_username):
    """Открывает диалог для выбора файла и отправляет его на сервер."""
    file_path, _ = QFileDialog.getOpenFileName(main_window, "Выберите файл")
    if file_path:
        file_name = os.path.basename(file_path)
        with open(file_path, 'rb') as file:
            file_data = file.read()
            # Отправляем файл на сервер
            sio.emit('file_upload', {'file_name': file_name, 'file_data': file_data, 'to': recipient_username})
        
        # Добавляем сообщение о загруженном файле в окно чата
        file_url = create_file_link(file_name)
        chat_box.append(f"<a href='{file_url}' style='color: {USER_COLOR}; text-decoration: none;'>Вы отправили файл: {file_name}</a>")
        chat_box.append("")  # Добавление пустой строки для форматирования



def open_registration_window():
    """Открывает окно регистрации."""
    global reg_window, reg_last_name_entry, reg_first_name_entry, reg_middle_name_entry, reg_birth_date_entry, reg_work_email_entry, reg_personal_email_entry, reg_phone_number_entry, reg_password_entry

    reg_window = QDialog(login_window)
    reg_window.setWindowTitle("Регистрация")
    reg_window.setStyleSheet(f"background-color: {BG_COLOR};")

    layout = QVBoxLayout()

    last_name_label = QLabel("Фамилия", reg_window)
    last_name_label.setStyleSheet(f"color: {HEADING_COLOR}; font-weight: bold;")
    layout.addWidget(last_name_label)

    reg_last_name_entry = QLineEdit(reg_window)
    reg_last_name_entry.setStyleSheet(f"background-color: {ENTRY_BG_COLOR}; border-radius: 10px; padding: 10px; color: {TEXT_COLOR};")
    layout.addWidget(reg_last_name_entry)

    first_name_label = QLabel("Имя", reg_window)
    first_name_label.setStyleSheet(f"color: {HEADING_COLOR}; font-weight: bold;")
    layout.addWidget(first_name_label)

    reg_first_name_entry = QLineEdit(reg_window)
    reg_first_name_entry.setStyleSheet(f"background-color: {ENTRY_BG_COLOR}; border-radius: 10px; padding: 10px; color: {TEXT_COLOR};")
    layout.addWidget(reg_first_name_entry)

    middle_name_label = QLabel("Отчество", reg_window)
    middle_name_label.setStyleSheet(f"color: {HEADING_COLOR}; font-weight: bold;")
    layout.addWidget(middle_name_label)

    reg_middle_name_entry = QLineEdit(reg_window)
    reg_middle_name_entry.setStyleSheet(f"background-color: {ENTRY_BG_COLOR}; border-radius: 10px; padding: 10px; color: {TEXT_COLOR};")
    layout.addWidget(reg_middle_name_entry)

    birth_date_label = QLabel("Дата рождения", reg_window)
    birth_date_label.setStyleSheet(f"color: {HEADING_COLOR}; font-weight: bold;")
    layout.addWidget(birth_date_label)

    reg_birth_date_entry = QLineEdit(reg_window)
    reg_birth_date_entry.setStyleSheet(f"background-color: {ENTRY_BG_COLOR}; border-radius: 10px; padding: 10px; color: {TEXT_COLOR};")
    layout.addWidget(reg_birth_date_entry)

    work_email_label = QLabel("Рабочая электронная почта", reg_window)
    work_email_label.setStyleSheet(f"color: {HEADING_COLOR}; font-weight: bold;")
    layout.addWidget(work_email_label)

    reg_work_email_entry = QLineEdit(reg_window)
    reg_work_email_entry.setStyleSheet(f"background-color: {ENTRY_BG_COLOR}; border-radius: 10px; padding: 10px; color: {TEXT_COLOR};")
    layout.addWidget(reg_work_email_entry)

    personal_email_label = QLabel("Личная электронная почта (по желанию)", reg_window)
    personal_email_label.setStyleSheet(f"color: {HEADING_COLOR}; font-weight: bold;")
    layout.addWidget(personal_email_label)

    reg_personal_email_entry = QLineEdit(reg_window)
    reg_personal_email_entry.setStyleSheet(f"background-color: {ENTRY_BG_COLOR}; border-radius: 10px; padding: 10px; color: {TEXT_COLOR};")
    layout.addWidget(reg_personal_email_entry)

    phone_number_label = QLabel("Номер телефона", reg_window)
    phone_number_label.setStyleSheet(f"color: {HEADING_COLOR}; font-weight: bold;")
    layout.addWidget(phone_number_label)

    reg_phone_number_entry = QLineEdit(reg_window)
    reg_phone_number_entry.setStyleSheet(f"background-color: {ENTRY_BG_COLOR}; border-radius: 10px; padding: 10px; color: {TEXT_COLOR};")
    layout.addWidget(reg_phone_number_entry)

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
    global all_user_data, unread_messages

    if isinstance(users, dict):
        # Объединяем данные о пользователях и непрочитанные сообщения
        all_user_data = [{'username': username, **details} for username, details in users.items()]
        unread_messages = {user['username']: unread_messages.get(user['username'], 0) for user in all_user_data}

        update_user_listbox()
    else:
        print("Unexpected data format:", users)

@sio.event
def unread_counts(data):
    global unread_messages
    if isinstance(data, dict):
        unread_messages.update(data)
        update_user_listbox()
    else:
        print("Unexpected data format:", data)

@sio.event
def global_message(data):
    """Обработчик для получения сообщений из общего чата."""
    if 'text' in data and 'sender' in data:
        text = data['text']
        sender = data['sender']

        # Добавляем сообщение с HTML-разметкой (ссылка будет кликабельной)
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
def file_received(data):
    """Обработчик для получения файлов."""
    from_user = data.get('from')
    file_name = data.get('file_name')
    file_url = create_file_link(file_name)  # Исправленный путь для доступа к файлам

    if file_name and file_url:
        # Вставляем кликабельную ссылку в чат
        link_html = f"<a href='{file_url}' style='color: {USER_COLOR}; text-decoration: none;'>{file_name}</a>"
        chat_box.append(f"{from_user}: Отправлен файл: {link_html}")
        chat_box.setTextInteractionFlags(Qt.TextBrowserInteraction)  # Разрешаем взаимодействие с текстом (клики по ссылкам)
        
        # Автоматически прокручиваем чат вниз
        chat_box.verticalScrollBar().setValue(chat_box.verticalScrollBar().maximum())
    else:
        chat_box.append(f"{from_user}: Получен файл, но имя файла или URL не указаны.")



def handle_link_click(url):
    """Обработчик кликов по ссылкам."""
    webbrowser.open(url.toString())  # Открывает ссылку в браузере


def open_link(url):
    """Открывает ссылку в веб-браузере."""
    webbrowser.open(url)

def handle_link_click(event):
    """Обработчик для открытия ссылок."""
    cursor = chat_box.textCursor()
    cursor.select(QTextCursor.LinkUnderCursor)
    link = cursor.selectedText()
    open_link(link)

@sio.event
def private_message(data):
    sender = data.get('from')
    recipient = data.get('to')
    message = data.get('text')
    file_name = data.get('file_name')
    file_data = data.get('file_data')

    if sender == current_username:
        return

    if recipient == current_username:
        if sender in private_chat_windows and private_chat_windows[sender]['window'].isVisible():
            private_chat_text_edit = private_chat_windows[sender]['text_edit']

            # Если сообщение содержит файл
            if file_name and file_data:
                save_file(file_name, file_data)
                file_url = create_file_link(file_name)
                private_chat_text_edit.append(f"{sender}: Отправлен файл: <a href='{file_url}' style='color: {USER_COLOR}; text-decoration: none;'>{file_name}</a>")
            else:
                private_chat_text_edit.append(f"{sender}: {message}")

            # Прокручиваем чат до самого низа
            scrollbar = private_chat_text_edit.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

            # Если окно чата с этим пользователем активно, не увеличиваем счетчик непрочитанных сообщений
            if private_chat_windows[sender]['window'].isVisible() and private_chat_windows[sender]['window'].isActiveWindow():
                unread_messages[sender] = 0
            else:
                unread_messages[sender] += 1

        else:
            # Увеличиваем счетчик непрочитанных сообщений, так как окно чата не активно или не существует
            unread_messages[sender] = unread_messages.get(sender, 0) + 1

        update_user_listbox()
    else:
        print(f"Чат с пользователем {sender} не открыт")

@sio.event
def message_received(data):
    sender = data.get('from')
    text = data.get('text')
    chat_type = data.get('type')

    if chat_type == 'private':
        unread_messages[sender] = unread_messages.get(sender, 0) + 1
        update_user_listbox()  # Обновляем список пользователей

    if chat_type == 'global':
        chat_box.append(f"{sender}: {text}")
    elif sender in private_chat_windows:
        private_chat_windows[sender]['text_edit'].append(f"{sender}: {text}")
        if private_chat_windows[sender]['window'].isVisible():
            unread_messages[sender] = 0
    else:
        update_user_listbox()

@sio.event
def chat_history(data):
    global history_loaded
    messages = data.get('messages', [])
    chat_type = data.get('type', 'unknown')
    username = data.get('username', '')

    if chat_type == 'global':
        if not history_loaded:
            for msg in messages:
                if 'file_name' in msg:
                    link_html = f"<a href='{msg.get('file_path')}' style='color: {USER_COLOR}; text-decoration: none;'>{msg.get('file_name')}</a>"
                    chat_box.append(f"{msg.get('sender', 'Unknown')}: Отправлен файл: {link_html}")
                else:
                    chat_box.append(f"{msg.get('sender', 'Unknown')}: {msg.get('text', '')}")
            
            scrollbar = chat_box.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            history_loaded = True
    elif chat_type == 'private' and username in private_chat_windows:
        text_edit = private_chat_windows[username]['text_edit']
        for msg in messages:
            if 'file_name' in msg:
                link_html = f"<a href='{msg.get('file_path')}' style='color: {USER_COLOR}; text-decoration: none;'>{msg.get('file_name')}</a>"
                text_edit.append(f"{msg.get('sender', 'Unknown')}: Отправлен файл: {link_html}")
            else:
                text_edit.append(f"{msg.get('sender', 'Unknown')}: {msg.get('text', '')}")

        # Прокрутка вниз
        scrollbar = text_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

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
    global user_listbox, all_user_data, unread_messages, private_chat_windows, current_username

    user_listbox.clear()

    if isinstance(all_user_data, list) and all(isinstance(user, dict) for user in all_user_data):
        for user in all_user_data:
            username = user.get('username')
            if username:
                item_text = username
                item = QListWidgetItem(item_text)

                # Проверяем, есть ли открытое окно чата и видимо ли оно
                if username in private_chat_windows and private_chat_windows[username]['window'].isVisible():
                    unread_messages[username] = 0

                # Добавляем символ, если есть непрочитанные сообщения
                if username != current_username and unread_messages.get(username, 0) > 0:
                    item_text += f" ⚠️ "
                    item.setText(item_text)
                    item.setForeground(QBrush(QColor("red")))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                else:
                    item.setForeground(QBrush(QColor(USER_COLOR)))

                user_listbox.addItem(item)
    else:
        print("Неверный формат данных о пользователях:", all_user_data)
def close_private_chat(username):
    """Функция для закрытия окна чата."""
    global chat_windows_state

    if username in private_chat_windows:
        private_chat_windows[username]['window'].close()
        chat_windows_state[username] = False  # Устанавливаем флаг как неактивное
        update_user_listbox()
    
def open_user_profile(username):
    """Открывает окно с информацией о пользователе."""
    # Получаем информацию о пользователе
    user_data = next((user for user in all_user_data if user['username'] == username), None)
    
    if not user_data:
        QMessageBox.critical(main_window, "Ошибка", "Не удалось загрузить данные пользователя")
        return
    
    profile_window = QDialog(main_window)
    profile_window.setWindowTitle(f"Профиль пользователя: {username}")
    profile_window.setStyleSheet(f"background-color: {BG_COLOR}; color: {TEXT_COLOR};")
    
    layout = QVBoxLayout()

    profile_text_browser = QTextBrowser()
    profile_text_browser.setOpenExternalLinks(True)  # Позволяет открывать ссылки во внешнем браузере
    profile_text_browser.setTextInteractionFlags(Qt.TextBrowserInteraction)  # Позволяет взаимодействие с текстом (выделение и копирование)
    profile_text_browser.setStyleSheet(f"""
        background-color: {ENTRY_BG_COLOR};
        border-radius: 10px;
        padding: 10px;
        color: white;
        border: 2px solid {BUTTON_COLOR};
    """)

    # Формируем HTML-код для QTextBrowser
    profile_text = f"""
    <html>
    <head>
        <style>
            .profile-label {{
                font-weight: bold;
                color: lightblue;  /* Светло-синий цвет для заголовков */
            }}
            .profile-value {{
                color: white;  /* Белый цвет для текста */
                background-color: {ENTRY_BG_COLOR};  /* Фоновый цвет для текста */
                padding: 5px;
                border: 1px solid {BUTTON_COLOR};  /* Рамка вокруг текста */
                border-radius: 5px;
                display: inline-block;
                margin-bottom: 5px;
            }}
            p {{
                margin: 0;  /* Убираем отступы вокруг параграфов */
            }}
        </style>
    </head>
    <body>
        <p><span class="profile-label">Фамилия:</span> <span class="profile-value">{user_data.get('last_name', 'Не указано')}</span></p>
        <p><span class="profile-label">Имя:</span> <span class="profile-value">{user_data.get('first_name', 'Не указано')}</span></p>
        <p><span class="profile-label">Отчество:</span> <span class="profile-value">{user_data.get('middle_name', 'Не указано')}</span></p>
        <p><span class="profile-label">Дата рождения:</span> <span class="profile-value">{user_data.get('birth_date', 'Не указано')}</span></p>
        <p><span class="profile-label">Рабочий email:</span> <span class="profile-value">{user_data.get('work_email', 'Не указано')}</span></p>
        <p><span class="profile-label">Личный email:</span> <span class="profile-value">{user_data.get('personal_email', 'Не указано')}</span></p>
        <p><span class="profile-label">Номер телефона:</span> <span class="profile-value">{user_data.get('phone_number', 'Не указано')}</span></p>
    </body>
    </html>
    """

    profile_text_browser.setHtml(profile_text)

    layout.addWidget(profile_text_browser)
    profile_window.setLayout(layout)
    profile_window.exec_()

def start_private_chat(username):
    global private_chat_windows

    # Если окно уже существует, просто делаем его видимым
    if username in private_chat_windows:
        private_chat_windows[username]['window'].show()
        private_chat_windows[username]['window'].raise_()
        private_chat_windows[username]['window'].activateWindow()
        
        # Сбрасываем количество непрочитанных сообщений при открытии окна
        unread_messages[username] = 0
        update_user_listbox()
        return

    # Создаем новое окно чата
    private_chat_window = QWidget()
    private_chat_window.setWindowTitle(f"Личный чат с {username}")
    private_chat_window.setStyleSheet(f"background-color: {BG_COLOR};")

    layout = QVBoxLayout(private_chat_window)

    text_edit = QTextBrowser()
    text_edit.setOpenExternalLinks(True)  # Позволяет открывать ссылки во внешнем браузере
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
        padding: 5px;
        color: {TEXT_COLOR};
        border: 2px solid {BUTTON_COLOR};
        border-top: 3px solid {BUTTON_HOVER_COLOR};
    """)
    input_layout.addWidget(private_message_entry)
    
    send_button = QPushButton("Отправить")
    send_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
    send_button.clicked.connect(lambda: send_private_message(username, private_message_entry))
    input_layout.addWidget(send_button)
    
    send_file_button = QPushButton("Отправить файл")
    send_file_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
    send_file_button.clicked.connect(lambda: send_private_file(username))
    input_layout.addWidget(send_file_button)
    
    emoji_button = QPushButton("😀")
    emoji_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
    emoji_button.clicked.connect(lambda: open_emoji_picker(private_message_entry))
    input_layout.addWidget(emoji_button)

    # Добавляем кнопку "Просмотр профиля"
    view_profile_button = QPushButton("Просмотр профиля")
    view_profile_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
    view_profile_button.clicked.connect(lambda: open_user_profile(username))
    input_layout.addWidget(view_profile_button)

    layout.addWidget(input_frame)

    # Добавляем информацию об окне в глобальный словарь
    private_chat_windows[username] = {
        'window': private_chat_window,
        'text_edit': text_edit,
        'message_entry': private_message_entry
    }

    # Запрашиваем историю чата
    sio.emit('request_chat_history', {'type': 'private', 'username': username})
    sio.emit('mark_messages_as_read', {'username': username})
    # Сбрасываем количество непрочитанных сообщений при открытии окна
    unread_messages[username] = 0
    update_user_listbox()

    # Показываем окно чата
    private_chat_window.show()
    private_chat_window.raise_()
    private_chat_window.activateWindow()

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

    # Заменяем QTextEdit на QTextBrowser
    chat_box = QTextBrowser()
    chat_box.setOpenExternalLinks(True)  # Включаем поддержку кликабельных ссылок
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

    # Создаем и настраиваем input_frame и его виджеты
    input_frame = QWidget()
    input_layout = QHBoxLayout(input_frame)

    message_entry = QTextEdit()
    message_entry.setStyleSheet(f"""
        background-color: {ENTRY_BG_COLOR};
        border-radius: 10px;
        padding: 5px;
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

    emoji_button = QPushButton("😀")
    emoji_button.setStyleSheet(f"background-color: {BUTTON_COLOR}; color: {TEXT_COLOR}; border-radius: 10px; padding: 10px;")
    emoji_button.clicked.connect(lambda: open_emoji_picker(message_entry))  # Передаем текстовое поле чата
    input_layout.addWidget(emoji_button)

    chat_layout.addWidget(input_frame)
    layout.addWidget(chat_frame)

    user_listbox.itemDoubleClicked.connect(lambda item: start_private_chat(item.text().split(' ')[0]))

    connect_socket()

    if not history_loaded:
        sio.emit('request_chat_history', {'type': 'global'})

    # Устанавливаем обработчик кликов по ссылкам
    chat_box.anchorClicked.connect(handle_link_click)

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
