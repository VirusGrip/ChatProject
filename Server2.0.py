from flask import Flask, request, jsonify, session, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room, send
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
import jwt

app = Flask(__name__)
app.secret_key = '12345678'
socketio = SocketIO(app, manage_session=True)

# Конфигурация загрузки файлов
UPLOAD_FOLDER = 'uploads'
HOST = '10.1.3.188:12345'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

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
                password TEXT NOT NULL,
                last_name TEXT,
                first_name TEXT,
                middle_name TEXT,
                birth_date DATE,
                work_email TEXT,
                personal_email TEXT,
                phone_number TEXT
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

@app.route('/check_token', methods=['GET'])
def check_token():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({"message": "Токен отсутствует"}), 401

    try:
        decoded = jwt.decode(token.split(' ')[1], app.secret_key, algorithms=['HS256'])
        return jsonify({"message": "Токен действителен"}), 200
    except jwt.ExpiredSignatureError:
        return jsonify({"message": "Токен истек"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"message": "Неверный токен"}), 401

def get_db():
    conn = sqlite3.connect(DATABASE)
    return conn, conn.cursor()

def get_chat_history(user_id, recipient_id):
    """Получаем историю приватного чата между двумя пользователями, включая ссылки на файлы."""
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

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"message": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"message": "No selected file"}), 400

    filename = secure_filename(file.filename)
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    
    print(f"Uploading file: {filename}, Path: {file_path}")
    
    file.save(file_path)

    # Формируем URL для доступа к файлу
    file_url = f"http://{HOST}/files/{filename}"

    # Оповещаем через сокет
    recipient = request.form.get('to')
    if recipient:
        conn, cur = get_db()
        cur.execute("SELECT id FROM users WHERE username = ?", (recipient,))
        recipient_data = cur.fetchone()
        if recipient_data:
            recipient_id = recipient_data[0]
            cur.execute("INSERT INTO files (user_id, recipient_id, file_path) VALUES (?, ?, ?)", 
                        (session['user_id'], recipient_id, filename))
            conn.commit()
            print(f"File record inserted: {filename}")
            recipient_sid = next((sid for sid, name in active_users.items() if name == recipient), None)
            if recipient_sid:
                emit('file_received', {'from': session['username'], 'file_url': file_url}, room=recipient_sid)
        conn.close()

    return jsonify({"file_url": file_url}), 200

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(file_path):
        return send_from_directory(UPLOAD_FOLDER, filename)
    else:
        return jsonify({"message": "File not found"}), 404

@app.route('/uploads/<filename>')
def download_file(filename):
    return send_from_directory('uploads', filename)
    
@socketio.on('file_received')
def handle_file_received(data):
    file_url = f"http://{HOST}/files/{data['file_path']}"
    emit('file_received', {'from': data['from'], 'file_url': file_url}, room=request.sid)

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    required_fields = ['last_name', 'first_name', 'middle_name', 'password']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'Ошибка: отсутствует обязательное поле {field}'}), 400

    username = f"{data['last_name']}{data['first_name'][0]}{data['middle_name'][0]}"
    password = data['password']
    hashed_password = generate_password_hash(password)

    conn, cur = get_db()
    try:
        cur.execute('''
            INSERT INTO users (
                username, password, last_name, first_name, middle_name, birth_date,
                work_email, personal_email, phone_number
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            username, hashed_password, data['last_name'], data['first_name'],
            data['middle_name'], data.get('birth_date'), data.get('work_email'),
            data.get('personal_email'), data.get('phone_number')
        ))
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
    cur.execute("SELECT id, username, last_name, first_name, middle_name, birth_date, work_email, personal_email, phone_number FROM users")
    users = cur.fetchall()
    conn.close()

    user_dict = {
        user[1]: {
            'id': user[0],
            'last_name': user[2],
            'first_name': user[3],
            'middle_name': user[4],
            'birth_date': user[5],
            'work_email': user[6],
            'personal_email': user[7],
            'phone_number': user[8]
        } 
        for user in users
    }
    return jsonify({'users': user_dict}), 200


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

            # Получаем всех пользователей
            cur.execute("SELECT id, username, last_name, first_name, middle_name, birth_date, work_email, personal_email, phone_number FROM users")
            users = cur.fetchall()
            user_dict = {
                user[1]: {
                    'id': user[0],
                    'last_name': user[2],
                    'first_name': user[3],
                    'middle_name': user[4],
                    'birth_date': user[5],
                    'work_email': user[6],
                    'personal_email': user[7],
                    'phone_number': user[8]
                } 
                for user in users
            }

            emit('all_users', user_dict, to=request.sid)

            # Получаем количество непрочитанных сообщений для текущего пользователя
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

            # Отправляем только непрочитанные сообщения
            cur.execute("""
                SELECT message, users.username 
                FROM private_messages 
                JOIN users ON users.id = private_messages.user_id 
                WHERE recipient_id = ? AND is_read = 0
            """, (session['user_id'],))
            unread_messages = cur.fetchall()
            for msg, sender in unread_messages:
                emit('private_message', {'from': sender, 'to': session['username'], 'text': msg})

            conn.close()

            emit('user_list', list(active_users.values()), broadcast=True)
            print(f"Пользователь {session['username']} подключен, session ID: {request.sid}")
        except jwt.ExpiredSignatureError:
            emit('error', {'message': 'Токен истек'})
        except jwt.InvalidTokenError:
            emit('error', {'message': 'Неверный токен'})
    else:
        emit('error', {'message': 'Необходим токен для подключения'})

@socketio.on('file_upload')
def handle_file_upload(data):
    username = session.get('username')
    file_name = data.get('file_name')
    file_data = data.get('file_data')

    if not username or not file_name or not file_data:
        emit('error', {'message': 'Ошибка: Вы не авторизованы или не указаны данные файла'})
        return

    file_path = os.path.join(UPLOAD_FOLDER, file_name)

    try:
        # Сохраняем файл на сервере
        with open(file_path, 'wb') as file:
            file.write(file_data)
        print(f"File saved: {file_name}")

        # Вставляем информацию о файле в базу данных
        user_id = session.get('user_id')
        file_url = f"http://{HOST}/files/{file_name}"
        html_message = f"<a href='{file_url}' style='color: #0077ff;'>{file_name}</a>"

        # Сохраняем сообщение как HTML-ссылку
        conn, cur = get_db()
        cur.execute("INSERT INTO global_messages (user_id, message) VALUES (?, ?)", (user_id, html_message))
        conn.commit()
        conn.close()

        # Оповещаем всех подключенных пользователей о новом файле
        emit('global_message', {'sender': username, 'text': html_message}, room='global_room')

    except Exception as e:
        emit('error', {'message': f'Ошибка сохранения файла: {str(e)}'})

@socketio.on('global_message')
def handle_global_message(data):
    username = session.get('username')
    message_text = data.get('text')

    if username and message_text:
        emit('global_message', {'sender': username, 'text': message_text}, room='global_room')
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

    # Если получатель подключен, отправляем ему сообщение
    if recipient_sid:
        emit('private_message', {'from': username, 'to': recipient, 'text': message_text}, room=recipient_sid)
    
    user_id = session.get('user_id')
    conn, cur = get_db()
    cur.execute("SELECT id FROM users WHERE username = ?", (recipient,))
    recipient_data = cur.fetchone()

    if recipient_data:
        recipient_id = recipient_data[0]
        cur.execute("INSERT INTO private_messages (user_id, recipient_id, message, is_read) VALUES (?, ?, ?, 0)", 
                    (user_id, recipient_id, message_text))
        conn.commit()

        # Обновляем количество непрочитанных сообщений для получателя
        cur.execute("""
            SELECT COUNT(id) FROM private_messages
            WHERE recipient_id = ? AND is_read = 0
        """, (recipient_id,))
        unread_count = cur.fetchone()[0]

        if recipient_sid:
            emit('unread_counts', {recipient: unread_count}, room=recipient_sid)
    else:
        emit('error', {'message': 'Ошибка: Получатель не найден в базе данных'})

    conn.close()

@socketio.on('private_file_upload_chunk')
def handle_private_file_upload_chunk(data):
    """Обрабатывает получение части файла."""
    recipient_username = data.get('to')
    file_name = data.get('file_name')
    file_data = data.get('file_data')  # Это часть данных
    chunk_index = data.get('chunk_index')
    total_chunks = data.get('total_chunks')
    sender_username = session.get('username')

    if not recipient_username or not file_name or not file_data:
        emit('error', {'message': 'Ошибка: данные файла или пользователя отсутствуют'})
        return

    # Временно сохраняем части файла
    temp_file_path = os.path.join(UPLOAD_FOLDER, f"{file_name}.part{chunk_index}")
    with open(temp_file_path, 'wb') as f:
        f.write(file_data)

    # Проверяем, получены ли все части
    if chunk_index + 1 == total_chunks:
        # Собираем файл
        final_file_path = os.path.join(UPLOAD_FOLDER, file_name)
        with open(final_file_path, 'wb') as final_file:
            for i in range(total_chunks):
                part_file_path = os.path.join(UPLOAD_FOLDER, f"{file_name}.part{i}")
                with open(part_file_path, 'rb') as part_file:
                    final_file.write(part_file.read())
                os.remove(part_file_path)  # Удаляем временные части

        # Формируем URL для файла
        file_url = f"http://{HOST}/uploads/{file_name}"

        # Находим ID отправителя и получателя
        conn, cur = get_db()
        cur.execute("SELECT id FROM users WHERE username = ?", (sender_username,))
        sender_id = cur.fetchone()[0]

        cur.execute("SELECT id FROM users WHERE username = ?", (recipient_username,))
        recipient_id = cur.fetchone()[0]

        # Сохраняем сообщение как ссылку на файл в базе данных
        message = f"<a href='{file_url}' style='color: #0077ff;'>{file_name}</a>"
        cur.execute("INSERT INTO private_messages (user_id, recipient_id, message, is_read) VALUES (?, ?, ?, 0)", 
                    (sender_id, recipient_id, message))
        conn.commit()

        # Оповещаем получателя о новом файле
        recipient_sid = next((sid for sid, name in active_users.items() if name == recipient_username), None)
        if recipient_sid:
            emit('private_message', {
                'from': sender_username, 
                'to': recipient_username, 
                'file_name': file_name, 
                'file_url': file_url
            }, room=recipient_sid)

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

    # Получаем историю чата
    chat_history = get_chat_history(user_id, recipient_id)
    formatted_history = [{'sender': sender, 'text': msg, 'timestamp': timestamp} for msg, timestamp, sender in chat_history]

    # Отправляем историю чата клиенту
    emit('chat_history', {'username': recipient_username, 'messages': formatted_history, 'type': 'private'}, room=request.sid)

    # Проверка данных перед обновлением
    cur.execute("""
        SELECT id, is_read, message 
        FROM private_messages 
        WHERE recipient_id = ? AND user_id = ? AND is_read = 0
    """, (user_id, recipient_id))
    unread_messages = cur.fetchall()
    print(f"Messages to be marked as read: {unread_messages}")

    # Упростим запрос на обновление, чтобы изолировать проблему
    cur.execute("""
        UPDATE private_messages 
        SET is_read = 1 
        WHERE recipient_id = ? AND user_id = ? AND is_read = 0
    """, (user_id, recipient_id))

    # Проверим, сколько строк было обновлено
    print(f"Messages marked as read: {cur.rowcount}")
    
    # Сохраняем изменения
    conn.commit()
    print("Changes committed to the database.")

    # Обновляем количество непрочитанных сообщений на клиенте
    cur.execute("""
        SELECT COUNT(id) 
        FROM private_messages 
        WHERE recipient_id = ? AND is_read = 0
    """, (user_id,))
    unread_count = cur.fetchone()[0]
    emit('unread_counts', {recipient_username: unread_count}, room=request.sid)

    conn.close()
@socketio.on('mark_messages_as_read')
def handle_mark_messages_as_read(data):
    recipient_username = session.get('username')
    sender_username = data.get('username')

    if not recipient_username or not sender_username:
        emit('error', {'message': 'Ошибка: Пользователь не найден'})
        return

    # Получение ID пользователей
    conn, cur = get_db()
    cur.execute("SELECT id FROM users WHERE username = ?", (sender_username,))
    sender = cur.fetchone()

    cur.execute("SELECT id FROM users WHERE username = ?", (recipient_username,))
    recipient = cur.fetchone()

    if not sender or not recipient:
        emit('error', {'message': 'Ошибка: Пользователь не найден'})
        return

    sender_id = sender[0]
    recipient_id = recipient[0]

    # Обновление статуса сообщений как прочитанных
    cur.execute("""
        UPDATE private_messages 
        SET is_read = 1 
        WHERE recipient_id = ? AND user_id = ? AND is_read = 0
    """, (recipient_id, sender_id))
    conn.commit()
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
    socketio.run(app, host='10.1.3.188', port=12345)
