import socket
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox

# Конфигурация клиента
HOST = '10.1.3.190'  # IP-адрес сервера
PORT = 12345  # Порт сервера

# Создание сокета
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((HOST, PORT))

# Глобальные переменные для окон
login_window = None
reg_window = None

def register():
    global reg_window

    username = reg_username_entry.get()
    password = reg_password_entry.get()

    if not username or not password:
        messagebox.showerror("Ошибка", "Введите логин и пароль!")
        return

    try:
        client.send("register".encode('utf-8'))  # Отправляем команду 'register'
        response = client.recv(1024).decode('utf-8')  # Ожидаем ответ от сервера

        if "Введите логин" in response:
            client.send(username.encode('utf-8'))
            response = client.recv(1024).decode('utf-8')  # Ожидаем ответ от сервера

            if "Введите пароль" in response:
                client.send(password.encode('utf-8'))
                response = client.recv(1024).decode('utf-8')

                if "успеш" in response.lower():
                    messagebox.showinfo("Успех", "Регистрация прошла успешно!")
                    reg_window.destroy()  # Закрываем окно регистрации
                    reg_window = None  # Обнуляем переменную
                else:
                    messagebox.showerror("Ошибка", response)
            else:
                messagebox.showerror("Ошибка", "Не удалось получить запрос на ввод пароля от сервера.")
        else:
            messagebox.showerror("Ошибка", "Не удалось получить запрос на ввод логина от сервера.")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Произошла ошибка при попытке регистрации: {e}")

def login():
    global login_window

    username = login_username_entry.get()
    password = login_password_entry.get()

    if not username or not password:
        messagebox.showerror("Ошибка", "Введите логин и пароль!")
        return

    try:
        client.send("login".encode('utf-8'))  # Отправляем команду 'login'
        response = client.recv(1024).decode('utf-8')  # Ожидаем ответ от сервера

        if "Введите логин" in response:
            client.send(username.encode('utf-8'))
            response = client.recv(1024).decode('utf-8')  # Ожидаем ответ от сервера

            if "Введите пароль" in response:
                client.send(password.encode('utf-8'))
                response = client.recv(1024).decode('utf-8')

                if "успеш" in response.lower():
                    login_window.destroy()  # Закрываем окно входа
                    login_window = None  # Обнуляем переменную
                    start_chat_interface()  # Запускаем интерфейс чата
                else:
                    messagebox.showerror("Ошибка", response)
            else:
                messagebox.showerror("Ошибка", "Не удалось получить запрос на ввод пароля от сервера.")
        else:
            messagebox.showerror("Ошибка", "Не удалось получить запрос на ввод логина от сервера.")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Произошла ошибка при попытке входа: {e}")

def receive_messages():
    while True:
        try:
            message = client.recv(1024).decode('utf-8')
            if not message:
                break
            chat_log.config(state=tk.NORMAL)
            chat_log.insert(tk.END, f"{message}\n")
            chat_log.config(state=tk.DISABLED)
        except:
            break

def send_message():
    message = message_entry.get()
    if message.lower() == 'exit':
        close_connection()
    else:
        try:
            client.send(message.encode('utf-8'))
            chat_log.config(state=tk.NORMAL)
            chat_log.insert(tk.END, f"Вы: {message}\n")
            chat_log.config(state=tk.DISABLED)
            message_entry.delete(0, tk.END)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось отправить сообщение: {e}")

def close_connection():
    global root

    try:
        client.close()
    except:
        pass
    if root is not None:
        root.destroy()
        root = None
    print("[-] Соединение закрыто")

receive_thread = threading.Thread(target=receive_messages)
receive_thread.start()

def start_chat_interface():
    global chat_log, message_entry, root

    root = tk.Tk()
    root.title(f"Клиент чата - {login_username_entry.get()}")

    chat_log = scrolledtext.ScrolledText(root, wrap=tk.WORD, state=tk.DISABLED, width=50, height=20)
    chat_log.grid(row=0, column=0, padx=10, pady=10, columnspan=2)

    message_entry = tk.Entry(root, width=40)
    message_entry.grid(row=1, column=0, padx=10, pady=5)

    send_button = tk.Button(root, text="Отправить", command=send_message)
    send_button.grid(row=1, column=1, padx=10, pady=5)

    exit_button = tk.Button(root, text="Выход", command=close_connection)
    exit_button.grid(row=2, column=0, padx=10, pady=5, columnspan=2)

    root.mainloop()

def start_login_interface():
    global login_window, login_username_entry, login_password_entry

    login_window = tk.Tk()
    login_window.title("Вход")

    tk.Label(login_window, text="Логин:").grid(row=0, column=0, padx=10, pady=5)
    login_username_entry = tk.Entry(login_window)
    login_username_entry.grid(row=0, column=1, padx=10, pady=5)

    tk.Label(login_window, text="Пароль:").grid(row=1, column=0, padx=10, pady=5)
    login_password_entry = tk.Entry(login_window, show='*')
    login_password_entry.grid(row=1, column=1, padx=10, pady=5)

    login_button = tk.Button(login_window, text="Вход", command=login)
    login_button.grid(row=2, column=0, columnspan=2, pady=10)

    reg_button = tk.Button(login_window, text="Регистрация", command=start_register_interface)
    reg_button.grid(row=3, column=0, columnspan=2, pady=10)

    login_window.mainloop()

def start_register_interface():
    global reg_window, reg_username_entry, reg_password_entry

    reg_window = tk.Tk()
    reg_window.title("Регистрация")

    tk.Label(reg_window, text="Логин:").grid(row=0, column=0, padx=10, pady=5)
    reg_username_entry = tk.Entry(reg_window)
    reg_username_entry.grid(row=0, column=1, padx=10, pady=5)

    tk.Label(reg_window, text="Пароль:").grid(row=1, column=0, padx=10, pady=5)
    reg_password_entry = tk.Entry(reg_window, show='*')
    reg_password_entry.grid(row=1, column=1, padx=10, pady=5)

    reg_button = tk.Button(reg_window, text="Регистрация", command=register)
    reg_button.grid(row=2, column=0, columnspan=2, pady=10)

    reg_window.mainloop()

start_login_interface()
