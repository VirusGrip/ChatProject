from flask import Flask, request, jsonify, session
from flask_socketio import SocketIO, send, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import jwt

app = Flask(__name__)
app.secret_key = '12345678'
socketio = SocketIO(app, manage_session=True)

DATABASE = 'chat.db'
active_users = {}  # Словарь для хранения активных пользователей и их сессий

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
                recipient_id INTEGER,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (recipient_id) REFERENCES users(id)
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
        return jsonify({'token': token}), 200
    else:
        return jsonify({'message': 'Неправильный логин или пароль'}), 400

# Получение списка всех пользователей
@app.route('/all_users', methods=['GET'])
def get_all_users():
    conn, cur = get_db()
    cur.execute("SELECT username FROM users")
    users = cur.fetchall()
    conn.close()

    user_list = [user[0] for user in users]
    return jsonify({'users': user_list}), 200

@socketio.on('connect')
def handle_connect():
    token = request.headers.get('Authorization')
    if token:
        try:
            decoded = jwt.decode(token.split(' ')[1], app.secret_key, algorithms=['HS256'])
            session['user_id'] = decoded['user_id']
            session['username'] = decoded['username']
            active_users[request.sid] = decoded['username']

            join_room('global_room')

            # Отправляем список всех пользователей
            conn, cur = get_db()
            cur.execute("SELECT username FROM users")
            users = cur.fetchall()

            user_list = [user[0] for user in users]
            emit('all_users', user_list, to=request.sid)

            # Получаем непрочитанные сообщения для пользователя
            cur.execute("SELECT message, users.username FROM messages JOIN users ON users.id = messages.user_id WHERE recipient_id = ? AND is_read = 0", 
                        (session['user_id'],))
            unread_messages = cur.fetchall()

            for msg, sender in unread_messages:
                emit('private_message', {'from': sender, 'to': session['username'], 'text': msg})

            # Обновляем статус сообщений как прочитанных
            cur.execute("UPDATE messages SET is_read = 1 WHERE recipient_id = ?", (session['user_id'],))
            conn.commit()

            conn.close()

            emit('user_list', list(active_users.values()), broadcast=True)
        except jwt.InvalidTokenError:
            send("Ошибка: Неверный токен", to=request.sid)
            return
    else:
        send("Ошибка: Вы не авторизованы", to=request.sid)
        return

@socketio.on('global_message')
def handle_global_message(data):
    username = session.get('username')
    message_text = data.get('text')

    # Отправка сообщения всем пользователям в общей комнате
    emit('message', f"[{username}] {message_text}", room='global_room')

    # Сохранение сообщения в базе данных
    user_id = session.get('user_id')
    if user_id:
        conn, cur = get_db()
        cur.execute("INSERT INTO messages (user_id, message) VALUES (?, ?)", (user_id, message_text))
        conn.commit()
        conn.close()
# Обработка выбора пользователя для чата
@socketio.on('select_user')
def handle_select_user(data):
    selected_user = data.get('username')
    if not selected_user:
        send("Ошибка: Пользователь не выбран", to=request.sid)
        return

    selected_sid = next((sid for sid, name in active_users.items() if name == selected_user), None)
    if selected_sid:
        # Формирование уникального имени комнаты
        room = f"room_{min(session['username'], selected_user)}_{max(session['username'], selected_user)}"
        join_room(room)
        emit('chat_started', {'room': room, 'username': selected_user}, room=request.sid)
    else:
        send("Ошибка: Пользователь не найден", to=request.sid)

@socketio.on('private_message')
def handle_private_message(data):
    username = session.get('username')
    recipient = data.get('to')
    message_text = data.get('text')

    if not username or not recipient:
        send("Ошибка: Вы не авторизованы или не указан получатель", to=request.sid)
        return

    room = f"room_{min(username, recipient)}_{max(username, recipient)}"
    join_room(room)

    # Проверяем, находится ли получатель в сети
    recipient_sid = next((sid for sid, name in active_users.items() if name == recipient), None)
    if recipient_sid:
        emit('private_message', {'from': username, 'to': recipient, 'text': message_text, 'room': room}, room=room)
        is_read = 1
    else:
        is_read = 0

    # Сохранение сообщения в базе данных
    user_id = session.get('user_id')
    conn, cur = get_db()
    cur.execute("SELECT id FROM users WHERE username = ?", (recipient,))
    recipient_data = cur.fetchone()

    if recipient_data:
        recipient_id = recipient_data[0]
        cur.execute("INSERT INTO messages (user_id, recipient_id, message, is_read) VALUES (?, ?, ?, ?)", 
                    (user_id, recipient_id, message_text, is_read))
        conn.commit()
    else:
        print("Ошибка: Получатель не найден в базе данных")

    conn.close()



# Обработка отключения
@socketio.on('disconnect')
def handle_disconnect():
    username = active_users.pop(request.sid, None)
    if username:
        # Оповещаем всех клиентов об обновлении списка пользователей
        emit('user_list', list(active_users.values()), broadcast=True)
        print(f"Пользователь {username} отключен, session ID: {request.sid}")

        # Удаление пользователя из всех комнат
        for room in list(socketio.server.manager.rooms.keys()):
            if room.startswith(f"room_{username}_") or room.endswith(f"_{username}"):
                leave_room(room)

# Запуск сервера
if __name__ == '__main__':
    init_db()
    socketio.run(app, host='10.1.3.187', port=12345)
