import socket
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox

HOST = '10.1.3.190'
PORT = 12345

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((HOST, PORT))

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
        client.send("register".encode('utf-8'))
        response = client.recv(1024).decode('utf-8')
        print(f"Received response: {response}")  # Отладочное сообщение

        if "Введите логин" in response:
            client.send(username.encode('utf-8'))
            response = client.recv(1024).decode('utf-8')
            print(f"Received response: {response}")  # Отладочное сообщение

            if "Введите пароль" in response:
                client.send(password.encode('utf-8'))
                response = client.recv(1024).decode('utf-8')
                print(f"Received response: {response}")  # Отладочное сообщение

                if "успеш" in response.lower():
                    messagebox.showinfo("Успех", "Регистрация прошла успешно!")
                    reg_window.destroy()
                    reg_window = None
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
        client.send("login".encode('utf-8'))
        response = client.recv(1024).decode('utf-8')
        print(f"Received response: {response}")  # Отладочное сообщение

        if "Введите логин" in response or "Вход успешен" in response:
            if "Введите логин" in response:
                client.send(username.encode('utf-8'))
                response = client.recv(1024).decode('utf-8')
                print(f"Received response: {response}")  # Отладочное сообщение

            if "Введите пароль" in response or "Вход успешен" in response:
                if "Введите пароль" in response:
                    client.send(password.encode('utf-8'))
                    response = client.recv(1024).decode('utf-8')
                    print(f"Received response: {response}")  # Отладочное сообщение

                if "успеш" in response.lower():
                    login_window.destroy()
                    login_window = None
                    start_chat_interface()
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

receive_thread = threading.Thread(target=receive_messages, daemon=True)
receive_thread.start()

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
