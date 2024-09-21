from flask import Flask, request, jsonify, session, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room, send
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import jwt
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = '12345678'
socketio = SocketIO(app, async_mode='gevent', manage_session=True)

# Конфигурация загрузки файлов
UPLOAD_FOLDER = 'uploads'
HOST = '192.168.1.127:12345'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Параметры подключения к PostgreSQL
DATABASE_URL = 'postgresql://postgres:123@localhost:5432/my_database'
active_users = {}  # Словарь для хранения активных пользователей и их сессий


def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn, conn.cursor()


def init_db():
    """Инициализация базы данных в PostgreSQL"""
    conn, cur = get_db()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
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
    cur.execute('''
        CREATE TABLE IF NOT EXISTS global_messages (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            message TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS private_messages (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            recipient_id INTEGER,
            message TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_read INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (recipient_id) REFERENCES users(id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            recipient_id INTEGER,
            file_path TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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


def get_chat_history(user_id, recipient_id):
    """Получаем историю приватного чата между двумя пользователями, включая ссылки на файлы."""
    conn, cur = get_db()
    cur.execute("""
        SELECT private_messages.message, private_messages.timestamp, sender.username as sender
        FROM private_messages
        JOIN users AS sender ON private_messages.user_id = sender.id
        WHERE (private_messages.user_id = %s AND private_messages.recipient_id = %s)
           OR (private_messages.user_id = %s AND private_messages.recipient_id = %s)
        ORDER BY private_messages.timestamp ASC
    """, (user_id, recipient_id, recipient_id, user_id))
    chat_history = cur.fetchall()
    conn.close()
    return chat_history


def get_global_chat_history():
    """Получаем историю глобального чата."""
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

    file.save(file_path)

    # Формируем URL для доступа к файлу
    file_url = f"http://{HOST}/uploads/{filename}"

    # Формируем HTML-ссылку
    html_message = f"<a href='{file_url}' style='color: #0077ff;'>{filename}</a>"

    # Оповещаем через сокет
    recipient = request.form.get('to')
    if recipient:
        conn, cur = get_db()
        cur.execute("SELECT id FROM users WHERE username = %s", (recipient,))
        recipient_data = cur.fetchone()
        if recipient_data:
            recipient_id = recipient_data['id']

            # Сохраняем ссылку на файл в БД как сообщение в виде HTML-ссылки
            cur.execute("INSERT INTO private_messages (user_id, recipient_id, message) VALUES (%s, %s, %s)",
                        (session['user_id'], recipient_id, html_message))
            conn.commit()

            recipient_sid = next((sid for sid, name in active_users.items() if name == recipient), None)
            if recipient_sid:
                emit('private_message', {'from': session['username'], 'text': html_message}, room=recipient_sid)
        conn.close()

    return jsonify({"file_url": file_url}), 200


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(file_path):
        return send_from_directory(UPLOAD_FOLDER, filename)
    else:
        return jsonify({"message": "File not found"}), 404


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
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            username, hashed_password, data['last_name'], data['first_name'],
            data['middle_name'], data.get('birth_date'), data.get('work_email'),
            data.get('personal_email'), data.get('phone_number')
        ))
        conn.commit()
        return jsonify({'message': 'Регистрация успешна!'}), 201
    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({'message': 'Пользователь с таким логином уже существует'}), 400
    finally:
        conn.close()


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data['username']
    password = data['password']

    conn, cur = get_db()
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    conn.close()

    if user and check_password_hash(user['password'], password):
        token = jwt.encode({'user_id': user['id'], 'username': username}, app.secret_key, algorithm='HS256')
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
        user['username']: {
            'id': user['id'],
            'last_name': user['last_name'],
            'first_name': user['first_name'],
            'middle_name': user['middle_name'],
            'birth_date': user['birth_date'],
            'work_email': user['work_email'],
            'personal_email': user['personal_email'],
            'phone_number': user['phone_number']
        }
        for user in users
    }
    return jsonify({'users': user_dict}), 200


@socketio.on('connect')
def handle_connect(auth):  # Добавляем аргумент
    print("Пользователь подключен через WebSocket")
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

            # Преобразуем дату в строку перед сериализацией
            user_dict = {
                user['username']: {
                    'id': user['id'],
                    'last_name': user['last_name'],
                    'first_name': user['first_name'],
                    'middle_name': user['middle_name'],
                    'birth_date': user['birth_date'].strftime('%Y-%m-%d') if user['birth_date'] else None,
                    'work_email': user['work_email'],
                    'personal_email': user['personal_email'],
                    'phone_number': user['phone_number']
                }
                for user in users
            }

            emit('all_users', user_dict, to=request.sid)

            # Остальная логика остается прежней
            cur.execute("""
                SELECT users.username, COUNT(private_messages.id) as unread_count
                FROM private_messages
                JOIN users ON users.id = private_messages.user_id
                WHERE private_messages.recipient_id = %s AND private_messages.is_read = 0
                GROUP BY users.username
            """, (session['user_id'],))
            unread_counts = cur.fetchall()
            unread_counts_dict = {row['username']: row['unread_count'] for row in unread_counts}
            emit('unread_counts', unread_counts_dict, room=request.sid)

            cur.execute("""
                SELECT message, users.username 
                FROM private_messages 
                JOIN users ON users.id = private_messages.user_id 
                WHERE recipient_id = %s AND is_read = 0
            """, (session['user_id'],))
            unread_messages = cur.fetchall()
            for msg in unread_messages:
                emit('private_message', {'from': msg['username'], 'to': session['username'], 'text': msg['message']})

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
        cur.execute("INSERT INTO global_messages (user_id, message) VALUES (%s, %s)", (user_id, html_message))
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
            cur.execute("INSERT INTO global_messages (user_id, message) VALUES (%s, %s)", (user_id, message_text))
            conn.commit()
            conn.close()
    else:
        emit('error', {'message': 'Ошибка: Вы не авторизованы или текст сообщения пустой'})


@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json
    username = data.get('sender')
    message_text = data.get('text')
    chat_type = data.get('type', 'global')

    if not username or not message_text:
        return jsonify({"message": "Отправитель или текст сообщения не указаны"}), 400

    conn, cur = get_db()

    if chat_type == 'global':
        # Получаем ID пользователя
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        user = cur.fetchone()

        if not user:
            return jsonify({"message": "Пользователь не найден"}), 404

        user_id = user['id']

        # Сохраняем сообщение в базе данных
        cur.execute("INSERT INTO global_messages (user_id, message) VALUES (%s, %s)", (user_id, message_text))
        conn.commit()
        conn.close()

        # Оповещаем всех пользователей
        socketio.emit('global_message', {'sender': username, 'text': message_text}, room='global_room')

    return jsonify({"message": "Сообщение отправлено"}), 200


@app.route('/request_chat_history', methods=['GET'])
def handle_chat_history_http():
    chat_type = request.args.get('type', 'global')

    if chat_type == 'global':
        # Получаем историю общего чата
        chat_history = get_global_chat_history()
        formatted_history = [{'sender': sender, 'text': message, 'timestamp': timestamp} for sender, message, timestamp in chat_history]
        return jsonify({'type': 'global', 'messages': formatted_history}), 200

    elif chat_type == 'private':
        recipient_username = request.args.get('username')
        if not recipient_username:
            return jsonify({'message': 'Пользователь не указан'}), 400

        conn, cur = get_db()
        cur.execute("SELECT id FROM users WHERE username = %s", (recipient_username,))
        recipient = cur.fetchone()

        if not recipient:
            return jsonify({'message': 'Пользователь не найден'}), 404

        recipient_id = recipient['id']
        user_id = session.get('user_id')

        # Получаем историю приватного чата
        chat_history = get_chat_history(user_id, recipient_id)
        formatted_history = [{'sender': sender, 'text': msg, 'timestamp': timestamp} for msg, timestamp, sender in chat_history]

        return jsonify({'username': recipient_username, 'messages': formatted_history, 'type': 'private'}), 200

    return jsonify({'message': 'Неверный тип чата'}), 400


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
        cur.execute("SELECT id FROM users WHERE username = %s", (recipient_username,))
        recipient = cur.fetchone()

        if not recipient:
            emit('error', {'message': 'Пользователь не найден'})
            return

        recipient_id = recipient['id']
        user_id = session['user_id']

        # Получаем историю приватного чата
        chat_history = get_chat_history(user_id, recipient_id)
        formatted_history = [{'sender': sender, 'text': msg, 'timestamp': timestamp} for msg, timestamp, sender in chat_history]

        emit('chat_history', {'username': recipient_username, 'messages': formatted_history, 'type': 'private'}, room=request.sid)
    else:
        emit('error', {'message': 'Неверный тип чата: ' + chat_type})


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
    cur.execute("SELECT id FROM users WHERE username = %s", (recipient,))
    recipient_data = cur.fetchone()

    if recipient_data:
        recipient_id = recipient_data['id']
        cur.execute("INSERT INTO private_messages (user_id, recipient_id, message, is_read) VALUES (%s, %s, %s, 0)",
                    (user_id, recipient_id, message_text))
        conn.commit()

        # Обновляем количество непрочитанных сообщений для получателя
        cur.execute("""
            SELECT COUNT(id) FROM private_messages
            WHERE recipient_id = %s AND is_read = 0
        """, (recipient_id,))
        unread_count = cur.fetchone()['count']

        if recipient_sid:
            emit('unread_counts', {recipient: unread_count}, room=recipient_sid)
    else:
        emit('error', {'message': 'Ошибка: Получатель не найден в базе данных'})

    conn.close()


@socketio.on('private_file_upload_chunk')
def handle_private_file_upload_chunk(data):
    file_name = data.get('file_name')
    file_data = data.get('file_data')
    chunk_index = data.get('chunk_index')
    total_chunks = data.get('total_chunks')
    recipient_username = data.get('to')
    sender_username = data.get('from')

    temp_file_path = os.path.join(UPLOAD_FOLDER, f"{file_name}.part{chunk_index}")
    with open(temp_file_path, 'wb') as f:
        f.write(file_data)

    # Проверяем, получены ли все части
    if chunk_index + 1 == total_chunks:
        final_file_path = os.path.join(UPLOAD_FOLDER, file_name)
        with open(final_file_path, 'wb') as final_file:
            for i in range(total_chunks):
                part_file_path = os.path.join(UPLOAD_FOLDER, f"{file_name}.part{i}")
                with open(part_file_path, 'rb') as part_file:
                    final_file.write(part_file.read())
                os.remove(part_file_path)  # Удаляем временные части

        # Формируем URL для файла
        file_url = f"http://{HOST}/uploads/{file_name}"

        # Формируем HTML-ссылку для вставки в БД
        html_message = f"<a href='{file_url}' style='color: #0077ff;'>{file_name}</a>"

        conn, cur = get_db()
        cur.execute("SELECT id FROM users WHERE username = %s", (recipient_username,))
        recipient = cur.fetchone()

        if recipient:
            recipient_id = recipient['id']
            user_id = session.get('user_id')

            # Сохраняем HTML-ссылку на файл в БД как сообщение
            cur.execute("INSERT INTO private_messages (user_id, recipient_id, message) VALUES (%s, %s, %s)",
                        (user_id, recipient_id, html_message))
            conn.commit()
            conn.close()

        # Оповещаем через сокет получателя
        recipient_sid = next((sid for sid, name in active_users.items() if name == recipient_username), None)
        if recipient_sid:
            emit('private_message', {'from': sender_username, 'file_name': file_name, 'file_url': file_url}, room=recipient_sid)


@socketio.on('file_upload_chunk')
def handle_file_upload_chunk(data):
    """Обрабатывает получение части файла для общего чата."""
    file_name = data.get('file_name')
    file_data = data.get('file_data')  # Это часть данных
    chunk_index = data.get('chunk_index')
    total_chunks = data.get('total_chunks')
    sender_username = session.get('username')

    if not file_name or not file_data:
        emit('error', {'message': 'Ошибка: данные файла отсутствуют'})
        return

    # Временно сохраняем части файла
    temp_file_path = os.path.join(UPLOAD_FOLDER, f"{file_name}.part{chunk_index}")
    with open(temp_file_path, 'wb') as f:
        f.write(file_data)

    # Проверяем, получены ли все части файла
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

        # Сохраняем информацию о файле в базе данных
        conn, cur = get_db()
        cur.execute("SELECT id FROM users WHERE username = %s", (sender_username,))
        user_id = cur.fetchone()['id']

        html_message = f"<a href='{file_url}' style='color: #0077ff;'>{file_name}</a>"

        # Сохраняем сообщение как HTML-ссылку в таблицу global_messages
        cur.execute("INSERT INTO global_messages (user_id, message) VALUES (%s, %s)", (user_id, html_message))
        conn.commit()

        conn.close()

        # Оповещаем всех подключенных пользователей о новом файле
        emit('global_message', {
            'sender': sender_username,
            'text': html_message
        }, room='global_room')


@socketio.on('start_private_chat')
def handle_start_private_chat(data):
    recipient_username = data.get('username')
    if not recipient_username:
        emit('error', {'message': 'Пользователь не указан'})
        return

    conn, cur = get_db()
    cur.execute("SELECT id FROM users WHERE username = %s", (recipient_username,))
    recipient = cur.fetchone()

    if not recipient:
        emit('error', {'message': 'Пользователь не найден'})
        return

    recipient_id = recipient['id']
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
        WHERE recipient_id = %s AND user_id = %s AND is_read = 0
    """, (user_id, recipient_id))
    unread_messages = cur.fetchall()
    print(f"Messages to be marked as read: {unread_messages}")

    # Обновляем статус прочитанных сообщений
    cur.execute("""
        UPDATE private_messages 
        SET is_read = 1 
        WHERE recipient_id = %s AND user_id = %s AND is_read = 0
    """, (user_id, recipient_id))

    print(f"Messages marked as read: {cur.rowcount}")
    conn.commit()

    # Обновляем количество непрочитанных сообщений на клиенте
    cur.execute("""
        SELECT COUNT(id) 
        FROM private_messages 
        WHERE recipient_id = %s AND is_read = 0
    """, (user_id,))
    unread_count = cur.fetchone()['count']
    emit('unread_counts', {recipient_username: unread_count}, room=request.sid)

    conn.close()


@socketio.on('logout')
def handle_logout(data):
    username = data.get('username')

    if username:
        # Получаем sid пользователя по его имени
        sid_to_remove = next((sid for sid, name in active_users.items() if name == username), None)

        if sid_to_remove:
            # Удаляем пользователя из списка активных
            active_users.pop(sid_to_remove, None)

            # Оповещаем остальных пользователей, что он отключен
            emit('user_list', list(active_users.values()), broadcast=True)
            print(f"Пользователь {username} отключен по запросу 'logout', session ID: {sid_to_remove}")

            # Отключаем сессию, передаем sid
            handle_disconnect(sid_to_remove)


@socketio.on('disconnect')
def handle_disconnect(sid=None):
    """Обработчик отключения пользователя."""
    if sid is None:
        sid = request.sid

    username = active_users.pop(sid, None)
    if username:
        emit('user_list', list(active_users.values()), broadcast=True)
        print(f"Пользователь {username} отключен, session ID: {sid}")

        for room in list(socketio.server.manager.rooms.keys()):
            if room.startswith(f"room_{username}_") or room.endswith(f"_{username}"):
                leave_room(room)


if __name__ == '__main__':
    init_db()
    socketio.run(app, host='192.168.1.127', port=12345)
