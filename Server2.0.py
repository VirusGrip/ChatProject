from flask import Flask, request, jsonify, session
from flask_socketio import SocketIO, send, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import threading
import os
import jwt  

app = Flask(__name__)
app.secret_key = '12345678'
socketio = SocketIO(app, manage_session=True)

DATABASE = 'chat.db'

# Инициализация базы данных
def init_db():
    if not os.path.exists(DATABASE):
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        conn.commit()
        conn.close()

# Подключение к базе данных
def get_db():
    conn = sqlite3.connect(DATABASE)
    return conn, conn.cursor()

# Регистрация пользователя
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data['username']
    password = data['password']
    hashed_password = generate_password_hash(password)

    conn, cur = get_db()
    try:
        cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
        return jsonify({'message': 'Регистрация успешна!'}), 201
    except sqlite3.IntegrityError:
        return jsonify({'message': 'Пользователь с таким логином уже существует'}), 400
    finally:
        conn.close()

# Вход пользователя
# Импорт JWT

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data['username']
    password = data['password']

    conn, cur = get_db()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cur.fetchone()
    conn.close()

    if user and check_password_hash(user[2], password):
        # Генерация JWT токена
        token = jwt.encode({'user_id': user[0], 'username': username}, app.secret_key, algorithm='HS256')
        return jsonify({'token': token}), 200  # Возвращаем токен в ответе
    else:
        return jsonify({'message': 'Неправильный логин или пароль'}), 400

# Обработка подключения к WebSocket
@socketio.on('connect')
def handle_connect():
    token = request.headers.get('Authorization')
    if token:
        try:
            # Декодируем токен
            decoded = jwt.decode(token.split(' ')[1], app.secret_key, algorithms=['HS256'])
            session['user_id'] = decoded['user_id']
            session['username'] = decoded['username']
            send(f"Пользователь {decoded['username']} с ID {decoded['user_id']} успешно подключен", to=request.sid)
        except jwt.InvalidTokenError:
            send("Ошибка: Неверный токен", to=request.sid)
            return
    else:
        send("Ошибка: Вы не авторизованы", to=request.sid)
        return

# Обработка сообщений
@socketio.on('message')
def handle_message(data):
    user_id = session.get('user_id')
    username = session.get('username')
    
    if not user_id:
        send("Ошибка: Вы не авторизованы", to=request.sid)
        return

    conn, cur = get_db()
    cur.execute("INSERT INTO messages (user_id, message) VALUES (?, ?)", (user_id, data['text']))
    conn.commit()
    conn.close()

    send(f"[{username}] {data['text']}", broadcast=True)

# Отправка истории сообщений при подключении
@socketio.on('join')
def handle_join():
    user_id = session.get('user_id')
    if not user_id:
        send("Ошибка: Вы не авторизованы", to=request.sid)
        return

    conn, cur = get_db()
    cur.execute("""
        SELECT messages.message, users.username, messages.timestamp 
        FROM messages JOIN users ON messages.user_id = users.id 
        ORDER BY messages.timestamp ASC
    """)
    chat_history = cur.fetchall()
    conn.close()

    for message in chat_history:
        send(f"[{message[1]}] {message[0]} ({message[2]})", to=request.sid)

# Обработка отключения
@socketio.on('disconnect')
def handle_disconnect():
    print(f"Пользователь {session.get('username')} с ID {session.get('user_id')} отключен, session ID: {request.sid}")

# Запуск сервера
if __name__ == '__main__':
    init_db()
    socketio.run(app, host='10.1.3.190', port=12345)
