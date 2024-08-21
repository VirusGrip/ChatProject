import socketio
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox
import requests

HOST = 'http://10.1.3.190:12345'
sio = socketio.Client()
token = None

login_window = None
reg_window = None
root = None
current_username = None  # Глобальная переменная для хранения имени пользователя

def register():
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
            current_username = username  # Сохраняем имя пользователя
            login_window.destroy()
            login_window = None
            sio.connect(HOST, headers={'Authorization': f'Bearer {token}'})  # Передаем токен при подключении
            start_chat_interface()
        else:
            messagebox.showerror("Ошибка", response.json().get('message', 'Ошибка входа'))
    except Exception as e:
        messagebox.showerror("Ошибка", f"Произошла ошибка при попытке входа: {e}")

@sio.event
def connect():
    print("Соединение с сервером установлено.")

@sio.event
def connect_error(data):
    print("Ошибка соединения с сервером:", data)

@sio.event
def disconnect():
    print("Соединение с сервером разорвано.")

def receive_messages():
    @sio.on('message')
    def on_message(data):
        def update_chat_log():
            username_in_message, message_text = data.split('] ', 1)
            username_in_message = username_in_message[1:]  # Убираем '[' в начале

            chat_log.config(state=tk.NORMAL)
            if username_in_message == current_username:
                chat_log.insert(tk.END, f"Вы: {message_text}\n")
            else:
                chat_log.insert(tk.END, f"{data}\n")
            chat_log.yview(tk.END)
            chat_log.config(state=tk.DISABLED)

        chat_log.after(0, update_chat_log)

def send_message():
    message = message_entry.get()
    if message.lower() == 'exit':
        close_connection()
    else:
        try:
            sio.emit('message', {'text': message})
            message_entry.delete(0, tk.END)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось отправить сообщение: {e}")

def close_connection():
    global root

    try:
        sio.disconnect()
    except:
        pass
    if root is not None:
        root.destroy()
        root = None
    print("[-] Соединение закрыто")

def start_chat_interface():
    global chat_log, message_entry, root

    root = tk.Tk()
    root.title("Чат")

    chat_log = scrolledtext.ScrolledText(root, state=tk.DISABLED)
    chat_log.pack(padx=10, pady=10)

    message_entry = tk.Entry(root, width=50)
    message_entry.pack(padx=10, pady=10)
    message_entry.bind("<Return>", lambda event: send_message())

    send_button = tk.Button(root, text="Отправить", command=send_message)
    send_button.pack(padx=10, pady=10)

    root.protocol("WM_DELETE_WINDOW", close_connection)

    # Запуск потока для приёма сообщений после инициализации GUI
    receive_thread = threading.Thread(target=receive_messages, daemon=True)
    receive_thread.start()

    root.mainloop()

def show_login_window():
    global login_window, login_username_entry, login_password_entry

    login_window = tk.Tk()
    login_window.title("Вход")

    tk.Label(login_window, text="Логин").pack(pady=5)
    login_username_entry = tk.Entry(login_window)
    login_username_entry.pack(pady=5)

    tk.Label(login_window, text="Пароль").pack(pady=5)
    login_password_entry = tk.Entry(login_window, show="*")
    login_password_entry.pack(pady=5)

    tk.Button(login_window, text="Вход", command=login).pack(pady=10)
    tk.Button(login_window, text="Регистрация", command=show_registration_window).pack(pady=10)

    login_window.mainloop()

def show_registration_window():
    global reg_window, reg_username_entry, reg_password_entry

    reg_window = tk.Tk()
    reg_window.title("Регистрация")

    tk.Label(reg_window, text="Логин").pack(pady=5)
    reg_username_entry = tk.Entry(reg_window)
    reg_username_entry.pack(pady=5)

    tk.Label(reg_window, text="Пароль").pack(pady=5)
    reg_password_entry = tk.Entry(reg_window, show="*")
    reg_password_entry.pack(pady=5)

    tk.Button(reg_window, text="Зарегистрироваться", command=register).pack(pady=10)

    reg_window.mainloop()

show_login_window()
