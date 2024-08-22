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
            messagebox.showerror("Ошибка", response.json().get('message', 'Ошибка регистрации'))
    except Exception as e:
        messagebox.showerror("Ошибка", f"Произошла ошибка при попытке регистрации: {e}")

def login():
    """Обработчик входа пользователя."""
    global login_window, login_username_entry, login_password_entry, token, current_username

    username = login_username_entry.get()
    password = login_password_entry.get()

    if not username or not password:
        messagebox.showerror("Ошибка", "Введите логин и пароль!")
        return

    try:
        response = requests.post(f"{HOST}/login", json={'username': username, 'password': password})
        if response.status_code == 200:
            token = response.json().get('token')
            current_username = username
            login_window.destroy()
            login_window = None
            sio.connect(HOST, headers={'Authorization': f'Bearer {token}'})
            start_chat_interface()
        else:
            messagebox.showerror("Ошибка", response.json().get('message', 'Ошибка входа'))
    except Exception as e:
        messagebox.showerror("Ошибка", f"Произошла ошибка при попытке входа: {e}")

@sio.event
def connect():
    """Обработчик события подключения к серверу."""
    print("Соединение с сервером установлено.")
    request_all_users()

@sio.event
def connect_error(data):
    """Обработчик события ошибки соединения с сервером."""
    print("Ошибка соединения с сервером:", data)

@sio.event
def disconnect():
    """Обработчик события отключения от сервера."""
    print("Соединение с сервером разорвано.")

@sio.event
def all_users(userList):
    """Обработчик получения списка всех зарегистрированных пользователей."""
    update_user_list(userList)

@sio.event
def message(data):
    """Обработка входящих сообщений."""
    def update_chat_log():
        chat_log.config(state=tk.NORMAL)
        chat_log.insert(tk.END, f"{data}\n")
        chat_log.config(state=tk.DISABLED)
        chat_log.see(tk.END)

    root.after(0, update_chat_log)

def request_all_users():
    """Запрос всех зарегистрированных пользователей с сервера."""
    try:
        print(f"Запрос списка всех пользователей с сервера...")  # Отладочная информация
        response = requests.get(f"{HOST}/all_users", headers={'Authorization': f'Bearer {token}'})
        if response.status_code == 200:
            global all_users
            all_users = response.json().get('users', [])
            print(f"Список пользователей с сервера: {all_users}")  # Отладочная информация
            update_user_list(all_users)  # Обновляем список всех пользователей
        else:
            messagebox.showerror("Ошибка", "Не удалось получить список пользователей.")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Произошла ошибка при запросе пользователей: {e}")

def update_user_list(users):
    """Обновление списка пользователей в интерфейсе."""
    print(f"Получен список пользователей: {users}")  # Отладочная информация
    if user_listbox:
        # Убедимся, что текущий пользователь есть в списке
        if current_username not in users:
            users.append(current_username)
            print(f"Добавлен текущий пользователь: {current_username}")  # Отладочная информация

        print(f"Планируем обновление Listbox через root.after с пользователями: {users}")
        root.after(0, lambda: _update_user_list_gui(users))  # Отложенное обновление GUI

def _update_user_list_gui(users):
    """Обновление Listbox в интерфейсе."""
    print(f"Обновление Listbox GUI: {users}")  # Отладочная информация
    if user_listbox is None:
        print("Listbox не был инициализирован!")  # Предупреждение
    else:
        user_listbox.delete(0, tk.END)  # Очистка списка
        for user in users:
            print(f"Добавление пользователя в Listbox: {user}")  # Отладочная информация
            user_listbox.insert(tk.END, user)  # Добавление пользователей в список
        user_listbox.update_idletasks()  # Обновление интерфейса

def send_message():
    """Отправка сообщения пользователю."""
    recipient = user_listbox.get(tk.ACTIVE)  # Получаем выбранного пользователя
    message_text = message_entry.get()
    if recipient and message_text:
        sio.emit('private_message', {'text': message_text, 'to': recipient})  # Отправка приватного сообщения
        message_entry.delete(0, tk.END)

def start_chat_interface():
    """Инициализация интерфейса чата."""
    global root, chat_log, message_entry, user_listbox

    print("Инициализация чата...")
    root = tk.Tk()
    root.title("Чат с личными сообщениями")

    chat_log = scrolledtext.ScrolledText(root, state=tk.DISABLED, width=50, height=20)
    chat_log.pack(padx=10, pady=10)

    message_entry = tk.Entry(root, width=40)
    message_entry.pack(side=tk.LEFT, padx=(10, 0))

    send_button = tk.Button(root, text="Отправить", command=send_message)
    send_button.pack(side=tk.LEFT, padx=(0, 10))

    user_listbox = tk.Listbox(root, width=20, height=20)
    user_listbox.pack(side=tk.RIGHT, padx=(0, 10))
    print("Listbox создан и размещен")

    user_listbox.bind('<Double-1>', start_private_chat)

    # Запрашиваем список всех пользователей после создания интерфейса
    root.after(1000, request_all_users)  # Используйте небольшую задержку для инициализации

    root.mainloop()

def start_private_chat(event):
    """Начинает приватный чат с пользователем по двойному клику."""
    selection = user_listbox.curselection()
    if selection:  # Проверяем, выбран ли элемент
        selected_user = user_listbox.get(selection[0])
        sio.emit('select_user', {'username': selected_user})
    else:
        messagebox.showinfo("Информация", "Пожалуйста, выберите пользователя из списка.")

def show_login_window():
    """Отображение окна входа."""
    global login_window, login_username_entry, login_password_entry

    login_window = tk.Tk()
    login_window.title("Вход")

    tk.Label(login_window, text="Логин").pack(padx=10, pady=(10, 0))
    login_username_entry = tk.Entry(login_window)
    login_username_entry.pack(padx=10, pady=(0, 10))

    tk.Label(login_window, text="Пароль").pack(padx=10, pady=(10, 0))
    login_password_entry = tk.Entry(login_window, show="*")
    login_password_entry.pack(padx=10, pady=(0, 10))

    login_button = tk.Button(login_window, text="Войти", command=login)
    login_button.pack(padx=10, pady=(10, 0))

    reg_button = tk.Button(login_window, text="Зарегистрироваться", command=show_registration_window)
    reg_button.pack(padx=10, pady=(10, 10))

    login_window.mainloop()

def show_registration_window():
    """Отображение окна регистрации."""
    global reg_window, reg_username_entry, reg_password_entry

    if reg_window is not None:
        return

    reg_window = tk.Toplevel()
    reg_window.title("Регистрация")

    tk.Label(reg_window, text="Логин").pack(padx=10, pady=(10, 0))
    reg_username_entry = tk.Entry(reg_window)
    reg_username_entry.pack(padx=10, pady=(0, 10))

    tk.Label(reg_window, text="Пароль").pack(padx=10, pady=(10, 0))
    reg_password_entry = tk.Entry(reg_window, show="*")
    reg_password_entry.pack(padx=10, pady=(0, 10))

    reg_button = tk.Button(reg_window, text="Зарегистрироваться", command=register)
    reg_button.pack(padx=10, pady=(10, 10))

    reg_window.mainloop()

if __name__ == '__main__':
    show_login_window()
