from flask import Flask, request, jsonify, session
from flask_socketio import SocketIO, send, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import jwt
import base64

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
            CREATE TABLE global_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE private_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                recipient_id INTEGER,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_read INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (recipient_id) REFERENCES users(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                recipient_id INTEGER,
                file_path TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (recipient_id) REFERENCES users(id)
            )
        ''')
        conn.commit()
        conn.close()

def get_chat_history(user_id, recipient_id):
    conn, cur = get_db()
    cur.execute("""
        SELECT private_messages.message, private_messages.timestamp, sender.username as sender
        FROM private_messages
        JOIN users AS sender ON private_messages.user_id = sender.id
        WHERE (private_messages.user_id = ? AND private_messages.recipient_id = ?)
           OR (private_messages.user_id = ? AND private_messages.recipient_id = ?)
        ORDER BY private_messages.timestamp ASC
    """, (user_id, recipient_id, recipient_id, user_id))
    chat_history = cur.fetchall()
    conn.close()
    return chat_history

def get_global_chat_history():
    conn, cur = get_db()
    cur.execute("""
        SELECT users.username, global_messages.message, global_messages.timestamp
        FROM global_messages
        JOIN users ON global_messages.user_id = users.id
        ORDER BY global_messages.timestamp ASC
    """)
    chat_history = cur.fetchall()
    conn.close()
    return chat_history

def get_db():
    conn = sqlite3.connect(DATABASE)
    return conn, conn.cursor()

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
        token = jwt.encode({'user_id': user[0], 'username': username}, app.secret_key, algorithm='HS256')
        return jsonify({'token': token}), 200
    else:
        return jsonify({'message': 'Неправильный логин или пароль'}), 400

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

            conn, cur = get_db()
            cur.execute("SELECT username FROM users")
            users = cur.fetchall()
            user_list = [user[0] for user in users]
            emit('all_users', user_list, to=request.sid)

            # Получаем количество непрочитанных сообщений
            cur.execute("""
                SELECT users.username, COUNT(private_messages.id) as unread_count
                FROM private_messages
                JOIN users ON users.id = private_messages.user_id
                WHERE private_messages.recipient_id = ? AND private_messages.is_read = 0
                GROUP BY users.username
            """, (session['user_id'],))
            unread_counts = cur.fetchall()
            unread_counts_dict = {username: count for username, count in unread_counts}
            emit('unread_counts', unread_counts_dict, room=request.sid)

            # Отправляем непрочитанные сообщения
            cur.execute("SELECT message, users.username FROM private_messages JOIN users ON users.id = private_messages.user_id WHERE recipient_id = ? AND is_read = 0", 
                        (session['user_id'],))
            unread_messages = cur.fetchall()
            for msg, sender in unread_messages:
                emit('private_message', {'from': sender, 'to': session['username'], 'text': msg})

            # Помечаем все непрочитанные сообщения как прочитанные
            cur.execute("UPDATE private_messages SET is_read = 1 WHERE recipient_id = ?", (session['user_id'],))
            conn.commit()
            conn.close()

            emit('user_list', list(active_users.values()), broadcast=True)
            emit('request_chat_history', {'type': 'global'}, room=request.sid)

        except jwt.InvalidTokenError:
            send("Ошибка: Неверный токен", to=request.sid)
            return
    else:
        send("Ошибка: Вы не авторизованы", to=request.sid)
        return

@socketio.on('upload_file')
def handle_upload_file(data):
    username = session.get('username')
    file_data = data.get('file')
    recipient = data.get('to')

    if not username or not file_data or not recipient:
        emit('error', {'message': 'Ошибка: Вы не авторизованы или не указаны данные файла'})
        return

    # Decode the file
    file_content = base64.b64decode(file_data['content'])
    file_name = file_data['name']
    file_path = f"uploads/{file_name}"
    
    # Save the file
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    
    with open(file_path, 'wb') as file:
        file.write(file_content)
    
    user_id = session.get('user_id')
    conn, cur = get_db()
    cur.execute("SELECT id FROM users WHERE username = ?", (recipient,))
    recipient_data = cur.fetchone()

    if recipient_data:
        recipient_id = recipient_data[0]
        cur.execute("INSERT INTO files (user_id, recipient_id, file_path) VALUES (?, ?, ?)", 
                    (user_id, recipient_id, file_path))
        conn.commit()
        conn.close()

        # Notify recipient
        recipient_sid = next((sid for sid, name in active_users.items() if name == recipient), None)
        if recipient_sid:
            emit('file_received', {'from': username, 'file_path': file_path}, room=recipient_sid)
    else:
        emit('error', {'message': 'Ошибка: Получатель не найден в базе данных'})

    conn.close()
    
@socketio.on('global_message')
def handle_global_message(data):
    username = session.get('username')
    message_text = data.get('text')

    if username and message_text:
        emit('global_message', {'sender': username, 'text': message_text}, room='global_room')  # Измените здесь
        # Сохраняем сообщение в базе данных
        user_id = session.get('user_id')
        if user_id:
            conn, cur = get_db()
            cur.execute("INSERT INTO global_messages (user_id, message) VALUES (?, ?)", (user_id, message_text))
            conn.commit()
            conn.close()
    else:
        emit('error', {'message': 'Ошибка: Вы не авторизованы или текст сообщения пустой'})

@socketio.on('request_chat_history')
def handle_request_chat_history(data):
    chat_type = data.get('type')
    
    if chat_type == 'global':
        chat_history = get_global_chat_history()
        formatted_history = [{'sender': sender, 'text': message, 'timestamp': timestamp} for sender, message, timestamp in chat_history]
        emit('chat_history', {'type': 'global', 'messages': formatted_history}, room=request.sid)
    elif chat_type == 'private':
        recipient_username = data.get('username')
        if not recipient_username:
            emit('error', {'message': 'Пользователь не указан'})
            return

        conn, cur = get_db()
        cur.execute("SELECT id FROM users WHERE username = ?", (recipient_username,))
        recipient = cur.fetchone()

        if not recipient:
            emit('error', {'message': 'Пользователь не найден'})
            return

        recipient_id = recipient[0]
        user_id = session['user_id']

        chat_history = get_chat_history(user_id, recipient_id)
        formatted_history = [{'sender': sender, 'text': msg, 'timestamp': timestamp} for msg, timestamp, sender in chat_history]

        emit('chat_history', {'username': recipient_username, 'messages': formatted_history, 'type': 'private'}, room=request.sid)
        conn.close()
    else:
        emit('error', {'message': 'Неверный тип чата: ' + chat_type})

@socketio.on('select_user')
def handle_select_user(data):
    selected_user = data.get('username')
    if not selected_user:
        send("Ошибка: Пользователь не выбран", to=request.sid)
        return

    selected_sid = next((sid for sid, name in active_users.items() if name == selected_user), None)
    if selected_sid:
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

    if not username or not recipient or not message_text:
        emit('error', {'message': 'Ошибка: Вы не авторизованы или не указан получатель'})
        return

    room = f"room_{min(username, recipient)}_{max(username, recipient)}"
    join_room(room)

    recipient_sid = next((sid for sid, name in active_users.items() if name == recipient), None)
    if recipient_sid:
        emit('private_message', {'from': username, 'to': recipient, 'text': message_text}, room=room)
        is_read = 0
    else:
        is_read = 0

    user_id = session.get('user_id')
    conn, cur = get_db()
    cur.execute("SELECT id FROM users WHERE username = ?", (recipient,))
    recipient_data = cur.fetchone()

    if recipient_data:
        recipient_id = recipient_data[0]
        cur.execute("INSERT INTO private_messages (user_id, recipient_id, message, is_read) VALUES (?, ?, ?, ?)", 
                    (user_id, recipient_id, message_text, is_read))
        conn.commit()

        # Обновляем количество непрочитанных сообщений для получателя
        cur.execute("""
            SELECT COUNT(id) FROM private_messages
            WHERE recipient_id = ? AND is_read = 0
        """, (recipient_id,))
        unread_count = cur.fetchone()[0]
        emit('unread_counts', {recipient: unread_count}, room=recipient_sid)
    else:
        emit('error', {'message': 'Ошибка: Получатель не найден в базе данных'})

    conn.close()

@socketio.on('start_private_chat')
def handle_start_private_chat(data):
    recipient_username = data.get('username')
    if not recipient_username:
        emit('error', {'message': 'Пользователь не указан'})
        return

    conn, cur = get_db()
    cur.execute("SELECT id FROM users WHERE username = ?", (recipient_username,))
    recipient = cur.fetchone()

    if not recipient:
        emit('error', {'message': 'Пользователь не найден'})
        return

    recipient_id = recipient[0]
    user_id = session['user_id']

    chat_history = get_chat_history(user_id, recipient_id)
    formatted_history = [{'sender': sender, 'text': msg, 'timestamp': timestamp} for msg, timestamp, sender in chat_history]

    emit('chat_history', {'username': recipient_username, 'messages': formatted_history, 'type': 'private'}, room=request.sid)

    conn.close()

@socketio.on('disconnect')
def handle_disconnect():
    username = active_users.pop(request.sid, None)
    if username:
        emit('user_list', list(active_users.values()), broadcast=True)
        print(f"Пользователь {username} отключен, session ID: {request.sid}")

        for room in list(socketio.server.manager.rooms.keys()):
            if room.startswith(f"room_{username}_") or room.endswith(f"_{username}"):
                leave_room(room)

 
if __name__ == '__main__':
    init_db()
    socketio.run(app, host='192.168.1.127', port=12345)