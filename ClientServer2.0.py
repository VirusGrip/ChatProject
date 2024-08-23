import socketio
import tkinter as tk
from tkinter import scrolledtext, messagebox
import requests

HOST = 'http://10.1.3.187:12345'
sio = socketio.Client()
token = None

login_window = None
reg_window = None
root = None
current_username = None
user_listbox = None
all_users = []  # Список всех зарегистрированных пользователей
private_chat_windows = {}  # Словарь для хранения ссылок на окна приватных чатов
unread_counts = {}  # Словарь для хранения количества непрочитанных сообщений

def register():
    """Обработчик регистрации нового пользователя."""
    global reg_window, reg_username_entry, reg_password_entry

    username = reg_username_entry.get()
    password = reg_password_entry.get()

    if not username or not password:
        messagebox.showerror("Ошибка", "Введите логин и пароль!")
        return

    try:
        response = requests.post(f"{HOST}/register", json={'username': username, 'password': password})
        if response.status_code == 201:
            messagebox.showinfo("Успех", "Регистрация прошла успешно!")
            reg_window.destroy()
            reg_window = None
        else:
            messagebox.showerror("Ошибка", response.json().get('message', 'Неизвестная ошибка'))
    except Exception as e:
        messagebox.showerror("Ошибка", str(e))

def open_registration_window():
    """Открывает окно регистрации."""
    global reg_window, reg_username_entry, reg_password_entry

    reg_window = tk.Toplevel(login_window)
    reg_window.title("Регистрация")

    tk.Label(reg_window, text="Логин").pack(pady=5)
    reg_username_entry = tk.Entry(reg_window)
    reg_username_entry.pack(padx=10, pady=5)

    tk.Label(reg_window, text="Пароль").pack(pady=5)
    reg_password_entry = tk.Entry(reg_window, show='*')
    reg_password_entry.pack(padx=10, pady=5)

    register_button = tk.Button(reg_window, text="Зарегистрироваться", command=register)
    register_button.pack(padx=10, pady=5)

    cancel_button = tk.Button(reg_window, text="Отмена", command=reg_window.destroy)
    cancel_button.pack(padx=10, pady=5)

def login():
    """Обработчик входа пользователя."""
    global login_window, username_entry, password_entry, token, current_username

    username = username_entry.get()
    password = password_entry.get()

    if not username or not password:
        messagebox.showerror("Ошибка", "Введите логин и пароль!")
        return

    try:
        response = requests.post(f"{HOST}/login", json={'username': username, 'password': password})
        if response.status_code == 200:
            token = response.json().get('token')
            current_username = username  # Сохраняем текущего пользователя
            login_window.destroy()
            login_window = None
            setup_main_window()
        else:
            messagebox.showerror("Ошибка", response.json().get('message', 'Неизвестная ошибка'))
    except Exception as e:
        messagebox.showerror("Ошибка", str(e))

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
    global all_users
    all_users = users
    update_user_listbox()

@sio.event
def unread_counts(counts):
    """Обработчик для получения количества непрочитанных сообщений от сервера."""
    global unread_counts
    unread_counts = {username: count for username, count in counts}
    update_user_listbox()

@sio.on('chat_history')
def handle_chat_history(data):
    username = data['username']
    messages = data['messages']

    if username in private_chat_windows:
        private_chat_listbox = private_chat_windows[username]['listbox']
        private_chat_listbox.config(state=tk.NORMAL)
        for msg in messages:
            private_chat_listbox.insert(tk.END, f"{msg['sender']}: {msg['text']}\n")
        private_chat_listbox.yview(tk.END)
        private_chat_listbox.config(state=tk.DISABLED)

@sio.event
def private_message(data):
    sender = data['from']
    recipient = data['to']
    message = data['text']

    if recipient == current_username:
        if sender in private_chat_windows:
            private_chat_listbox = private_chat_windows[sender]['listbox']
            private_chat_listbox.config(state=tk.NORMAL)
            private_chat_listbox.insert(tk.END, f"{sender}: {message}\n")
            private_chat_listbox.yview(tk.END)
            private_chat_listbox.config(state=tk.DISABLED)

def send_message():
    """Отправка сообщения в общий чат."""
    message = message_entry.get()
    if not message:
        return

    sio.emit('global_message', {'text': message})
    message_entry.delete(0, tk.END)

def start_private_chat(username):
    """Начало приватного чата с выбранным пользователем и загрузка истории."""
    global private_chat_windows

    if username in private_chat_windows:
        # Если чат с пользователем уже открыт, просто фокусируемся на нем
        private_chat_windows[username]['window'].lift()
        return

    private_chat_window = tk.Toplevel(root)
    private_chat_window.title(f"Чат с {username}")

    private_chat_listbox = scrolledtext.ScrolledText(private_chat_window, state=tk.DISABLED)
    private_chat_listbox.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

    private_message_entry = tk.Entry(private_chat_window)
    private_message_entry.pack(padx=10, pady=5, fill=tk.X, expand=True)
    private_message_entry.bind('<Return>', lambda event: send_private_message(username))

    send_button = tk.Button(private_chat_window, text="Отправить", command=lambda: send_private_message(username))
    send_button.pack(padx=10, pady=5)

    private_chat_windows[username] = {
        'window': private_chat_window,
        'listbox': private_chat_listbox,
        'entry': private_message_entry
    }

    # Запрашиваем историю сообщений
    sio.emit('start_private_chat', {'username': username})

def send_private_message(username):
    """Отправка приватного сообщения и отображение его в чате."""
    message = private_chat_windows[username]['entry'].get()
    if not message:
        return

    # Отправляем сообщение через сокет
    sio.emit('private_message', {'to': username, 'text': message})

    # Отображаем сообщение в чате как "Вы"
    private_chat_listbox = private_chat_windows[username]['listbox']
    private_chat_listbox.config(state=tk.NORMAL)
    private_chat_listbox.insert(tk.END, f"Вы: {message}\n")
    private_chat_listbox.yview(tk.END)
    private_chat_listbox.config(state=tk.DISABLED)

    # Очищаем поле ввода
    private_chat_windows[username]['entry'].delete(0, tk.END)

def update_user_listbox():
    """Обновление списка пользователей с учётом количества непрочитанных сообщений."""
    global user_listbox, all_users, unread_counts

    user_listbox.delete(0, tk.END)
    for user in all_users:
        display_name = user
        if user in unread_counts:
            display_name += f" ({unread_counts[user]} непрочитанных)"
        user_listbox.insert(tk.END, display_name)

def setup_main_window():
    """Настройка основного окна приложения."""
    global root, chat_box, message_entry, user_listbox

    root = tk.Tk()
    root.title("Чат")

    # Окно чата
    chat_frame = tk.Frame(root)
    chat_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

    chat_box = scrolledtext.ScrolledText(chat_frame, state=tk.DISABLED)
    chat_box.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

    message_entry = tk.Entry(root)
    message_entry.pack(padx=10, pady=5, fill=tk.X, expand=True)
    message_entry.bind('<Return>', lambda event: send_message())

    send_button = tk.Button(root, text="Отправить", command=send_message)
    send_button.pack(padx=10, pady=5)

    # Список пользователей
    user_frame = tk.Frame(root)
    user_frame.pack(padx=10, pady=5, fill=tk.Y, side=tk.LEFT)

    tk.Label(user_frame, text="Пользователи").pack(pady=5)
    user_listbox = tk.Listbox(user_frame)
    user_listbox.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
    user_listbox.bind('<Double-1>', lambda event: start_private_chat(user_listbox.get(user_listbox.curselection()).split(' ')[0]))

    connect_socket()

    root.mainloop()

if __name__ == "__main__":
    login_window = tk.Tk()
    login_window.title("Вход")

    tk.Label(login_window, text="Логин").pack(pady=5)
    username_entry = tk.Entry(login_window)
    username_entry.pack(padx=10, pady=5)

    tk.Label(login_window, text="Пароль"). pack(pady=5)
    password_entry = tk.Entry(login_window, show='*')
    password_entry.pack(padx=10, pady=5)

    login_button = tk.Button(login_window, text="Войти", command=login)
    login_button.pack(padx=10, pady=5)

    reg_button = tk.Button(login_window, text="Регистрация", command=open_registration_window)
    reg_button.pack(padx=10, pady=5)

    login_window.mainloop()
