import socket
import threading
import json
import os

clients = []
usernames = {}

USERS_FILE = 'users.json'
users_lock = threading.Lock()

def load_users():
    with users_lock:
        try:
            if os.path.exists(USERS_FILE):
                with open(USERS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"[-] Ошибка при загрузке данных пользователей: {e}")
            return {}

def save_users(users):
    with users_lock:
        try:
            with open(USERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(users, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[-] Ошибка при сохранении данных пользователей: {e}")

def handle_client(client_socket, addr):
    print(f"[+] Новое соединение от {addr}")
    
    try:
        client_socket.send("Введите 'register' для регистрации или 'login' для входа:".encode('utf-8'))
        mode = client_socket.recv(1024).decode('utf-8').strip().lower()

        if mode not in ['register', 'login']:
            client_socket.send("Неправильная команда. Соединение закрыто.".encode('utf-8'))
            client_socket.close()
            return

        client_socket.send("Введите логин:".encode('utf-8'))
        username = client_socket.recv(1024).decode('utf-8').strip()

        client_socket.send("Введите пароль:".encode('utf-8'))
        password = client_socket.recv(1024).decode('utf-8').strip()

        if mode == 'register':
            if register_user(client_socket, username, password):
                usernames[client_socket] = username
                clients.append(client_socket)
                client_socket.send("Вход успешен!".encode('utf-8'))  # Убедимся, что сообщение отправляется
                handle_messages(client_socket, addr)
        elif mode == 'login':
            if authenticate_user(client_socket, username, password):
                usernames[client_socket] = username
                clients.append(client_socket)
                client_socket.send("Вход успешен!".encode('utf-8'))  # Убедимся, что сообщение отправляется
                handle_messages(client_socket, addr)
        else:
            client_socket.send("Неизвестный режим. Соединение закрыто.".encode('utf-8'))
            client_socket.close()
    except Exception as e:
        print(f"[-] Ошибка обработки клиента {addr}: {e}")
    finally:
        if client_socket in clients:
            clients.remove(client_socket)
        client_socket.close()

def handle_messages(client_socket, addr):
    while True:
        try:
            message = client_socket.recv(1024).decode('utf-8')
            if not message:
                break

            print(f"[{usernames[client_socket]}] {message}")
            broadcast(f"[{usernames[client_socket]}] {message}", client_socket)
        except Exception as e:
            print(f"[-] Ошибка обработки сообщения от {addr}: {e}")
            break

    print(f"[-] Соединение с {addr} закрыто")
    clients.remove(client_socket)
    client_socket.close()

def broadcast(message, sender_socket):
    for client in clients:
        if client != sender_socket:
            try:
                client.send(message.encode('utf-8'))
            except Exception as e:
                print(f"[-] Ошибка при отправке сообщения: {e}")
                clients.remove(client)
                client.close()

def register_user(client_socket, username, password):
    users = load_users()
    
    if username in users:
        client_socket.send("Пользователь с таким логином уже существует".encode('utf-8'))
        return False
    else:
        users[username] = password
        save_users(users)
        client_socket.send("Регистрация успешна!".encode('utf-8'))
        return True

def authenticate_user(client_socket, username, password):
    users = load_users()
    
    if username in users and users[username] == password:
        client_socket.send("Вход успешен!".encode('utf-8'))
        return True
    else:
        client_socket.send("Неправильный логин или пароль".encode('utf-8'))
        return False

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('10.1.3.190', 12345))
    server.listen(5)
    print("[*] Сервер запущен на порту 12345")

    while True:
        client_socket, addr = server.accept()
        client_thread = threading.Thread(target=handle_client, args=(client_socket, addr))
        client_thread.start()

start_server()
