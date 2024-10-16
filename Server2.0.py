import logging
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, session, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room, send
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import psycopg2
import os
import jwt

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = '12345678'
socketio = SocketIO(app, manage_session=True)

# Конфигурация загрузки файлов
UPLOAD_FOLDER = 'uploads'
HOST = '192.168.1.127:12345'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

DATABASE = {
    'dbname': 'chat_project',
    'user': 'postgres',
    'password': '123',
    'host': 'localhost',
    'port': '5432'
}
active_users = {}  # Словарь для хранения активных пользователей и их сессий

def get_db():
    """Функция для получения подключения к базе данных с использованием пула соединений."""
    try:
        conn = psycopg2.connect(**DATABASE)
        logger.info("Подключение к базе данных успешно установлено")
        return conn, conn.cursor()
    except psycopg2.Error as e:
        logger.error(f"Ошибка подключения к базе данных: {e}")
        raise
def init_db():
    """Инициализация базы данных"""
    conn, cursor = get_db()
    try:
        cursor.execute('''
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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS global_messages (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                message TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS private_messages (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                recipient_id INTEGER,
                message TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_read BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (recipient_id) REFERENCES users(id)
            )
        ''')
        cursor.execute('''
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
        logger.info("База данных успешно инициализирована")
    except psycopg2.Error as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
@app.route('/login', methods=['POST'])
def login():
    logger.info("Получен запрос на вход")
    data = request.json
    logger.info(f"Данные для входа: {data}")

    if 'username' not in data or 'password' not in data:
        logger.warning("Ошибка: отсутствует обязательное поле 'username' или 'password'")
        return jsonify({'message': 'Ошибка: отсутствует обязательное поле "username" или "password"'}), 400

    username = data['username']
    password = data['password']

    conn, cur = get_db()
    try:
        cur.execute("SELECT id, password FROM users WHERE username = %s", (username,))
        user_data = cur.fetchone()
        if user_data is None:
            logger.warning(f"Пользователь {username} не найден")
            return jsonify({'message': 'Неверный логин или пароль'}), 401

        user_id, hashed_password = user_data
        if not check_password_hash(hashed_password, password):
            logger.warning(f"Неверный пароль для пользователя {username}")
            return jsonify({'message': 'Неверный логин или пароль'}), 401

        # Создание JWT токена
        token = jwt.encode(
            {
                'user_id': user_id,
                'username': username,
                'exp': datetime.now(timezone.utc) + timedelta(hours=1)  # Обновлено
            },
            app.secret_key,
            algorithm='HS256'
        )

        logger.info(f"Пользователь {username} успешно вошел")
        return jsonify({'token': token}), 200

    except psycopg2.Error as e:
        logger.error(f"Ошибка базы данных при входе пользователя {username}: {e}")
        return jsonify({'message': f'Ошибка базы данных: {e}'}), 500
    finally:
        cur.close()
        conn.close()
@app.route('/check_token', methods=['GET'])
def check_token():
    logger.info("Получен запрос на проверку токена")
    token = request.headers.get('Authorization')
    if not token:
        logger.warning("Токен отсутствует")
        return jsonify({"message": "Токен отсутствует"}), 401

    try:
        decoded = jwt.decode(token.split(' ')[1], app.secret_key, algorithms=['HS256'])
        logger.info("Токен действителен")
        return jsonify({"message": "Токен действителен"}), 200
    except jwt.ExpiredSignatureError:
        logger.warning("Токен истек")
        return jsonify({"message": "Токен истек"}), 401
    except jwt.InvalidTokenError:
        logger.warning("Неверный токен")
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
    cur.close()
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
    # Преобразуем datetime в строку перед возвращением
    formatted_history = [(username, message, str(timestamp)) for username, message, timestamp in chat_history]
    cur.close()
    conn.close()
    return formatted_history

@app.route('/register', methods=['POST'])
def register():
    logger.info("Получен запрос на регистрацию")
    data = request.json
    logger.info(f"Данные для регистрации: {data}")

    required_fields = ['last_name', 'first_name', 'middle_name', 'password']
    for field in required_fields:
        if field not in data:
            logger.warning(f"Ошибка: отсутствует обязательное поле {field}")
            return jsonify({'message': f'Ошибка: отсутствует обязательное поле {field}'}), 400

    username = f"{data['last_name']}{data['first_name'][0]}{data['middle_name'][0]}"
    password = data['password']
    hashed_password = generate_password_hash(password)

    conn, cur = None, None
    try:
        conn, cur = get_db()
        cur.execute('''
            INSERT INTO users (
                username, password, last_name, first_name, middle_name, birth_date,
                work_email, personal_email, phone_number
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            username, hashed_password, data['last_name'], data['first_name'],
            data['middle_name'], data.get('birth_date'), data.get('work_email'),
            data.get('personal_email'), data.get('phone_number')
        ))
        conn.commit()
        logger.info("Регистрация успешна")
        return jsonify({'message': 'Регистрация успешна!'}), 201
    except psycopg2.IntegrityError:
        if conn:
            conn.rollback()
        logger.warning("Пользователь с таким логином уже существует")
        return jsonify({'message': 'Пользователь с таким логином уже существует'}), 400
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Ошибка базы данных: {e}")
        return jsonify({'message': f'Ошибка базы данных: {e}'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# Функция для получения истории глобального чата
def get_global_chat_history():
    conn, cur = get_db()
    cur.execute("""
        SELECT users.username, global_messages.message, global_messages.timestamp
        FROM global_messages
        JOIN users ON global_messages.user_id = users.id
        ORDER BY global_messages.timestamp ASC
    """)
    chat_history = cur.fetchall()
    cur.close()
    conn.close()
    return chat_history
@app.route('/uploads/<path:filename>', methods=['GET'])
def download_file(filename):
    """Обрабатывает запросы для скачивания файлов из папки uploads."""
    try:
        return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=False)
    except FileNotFoundError:
        return jsonify({"message": "Файл не найден"}), 404
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
            recipient_id = recipient_data[0]

            # Сохраняем ссылку на файл в БД как сообщение в виде HTML-ссылки
            cur.execute("INSERT INTO private_messages (user_id, recipient_id, message) VALUES (%s, %s, %s)", 
                        (session['user_id'], recipient_id, html_message))
            conn.commit()

            recipient_sid = next((sid for sid, name in active_users.items() if name == recipient), None)
            if recipient_sid:
                emit('private_message', {'from': session['username'], 'text': html_message}, room=recipient_sid)
        cur.close()
        conn.close()

    return jsonify({"file_url": file_url}), 200

@app.route('/all_users', methods=['GET'])
def get_all_users():
    logger.info("Получен запрос на получение всех пользователей")
    conn, cur = get_db()
    try:
        cur.execute("SELECT id, username, last_name, first_name, middle_name, birth_date, work_email, personal_email, phone_number FROM users")
        users = cur.fetchall()
        logger.info(f"Получены пользователи: {users}")

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
    except psycopg2.Error as e:
        logger.error(f"Ошибка получения пользователей: {e}")
        return jsonify({'message': f'Ошибка получения пользователей: {e}'}), 500
    finally:
        cur.close()
        conn.close()

@socketio.on('connect')
def handle_connect(sid):
    token = request.headers.get('Authorization')
    if token:
        try:
            decoded = jwt.decode(token.split(' ')[1], app.secret_key, algorithms=['HS256'])
            session['user_id'] = decoded['user_id']
            session['username'] = decoded['username']
            active_users[sid] = decoded['username']

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
                    'birth_date': str(user[5]) if user[5] else None,  # Преобразуем дату в строку
                    'work_email': user[6],
                    'personal_email': user[7],
                    'phone_number': user[8]
                }
                for user in users
            }

            # Отправляем список всех пользователей клиенту
            emit('all_users', user_dict, to=sid)

            # Получаем количество непрочитанных сообщений для текущего пользователя
            cur.execute("""
                SELECT users.username, COUNT(private_messages.id) as unread_count
                FROM private_messages
                JOIN users ON users.id = private_messages.user_id
                WHERE private_messages.recipient_id = %s AND private_messages.is_read = FALSE
                GROUP BY users.username
            """, (session['user_id'],))
            unread_counts = cur.fetchall()
            unread_counts_dict = {username: count for username, count in unread_counts}
            emit('unread_counts', unread_counts_dict, room=sid)

            # Отправляем только непрочитанные сообщения
            cur.execute("""
                SELECT message, users.username 
                FROM private_messages 
                JOIN users ON users.id = private_messages.user_id 
                WHERE recipient_id = %s AND is_read = FALSE
            """, (session['user_id'],))
            unread_messages = cur.fetchall()
            for msg, sender in unread_messages:
                emit('private_message', {'from': sender, 'to': session['username'], 'text': msg}, room=sid)

            cur.close()
            conn.close()

            # Оповещаем всех пользователей о новом пользователе
            emit('user_list', list(active_users.values()), broadcast=True)
            logger.info(f"Пользователь {session['username']} подключен, session ID: {sid}")
        except jwt.ExpiredSignatureError:
            emit('error', {'message': 'Токен истек'}, room=sid)
        except jwt.InvalidTokenError:
            emit('error', {'message': 'Неверный токен'}, room=sid)
    else:
        emit('error', {'message': 'Необходим токен для подключения'}, room=sid)

@socketio.on('global_message')
def handle_global_message(data):
    # Получаем сообщение и имя отправителя
    message_text = data.get('text')
    sender_username = data.get('sender')

    if not message_text or not sender_username:
        emit('error', {'message': 'Неверные данные для сообщения'})
        return

    # Сохранение в базу данных
    conn, cur = get_db()
    try:
        # Ищем ID пользователя по его имени
        cur.execute("SELECT id FROM users WHERE username = %s", (sender_username,))
        user_id = cur.fetchone()
        if user_id is None:
            emit('error', {'message': 'Пользователь не найден'})
            return
        user_id = user_id[0]

        # Вставляем сообщение в таблицу global_messages
        cur.execute("INSERT INTO global_messages (user_id, message) VALUES (%s, %s)", (user_id, message_text))
        conn.commit()

        # Транслируем сообщение всем подключенным пользователям
        emit('global_message', {'sender': sender_username, 'text': message_text}, room='global_room')
    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"Ошибка базы данных при сохранении сообщения в глобальный чат: {e}")
        emit('error', {'message': 'Ошибка базы данных при сохранении сообщения'})
    finally:
        cur.close()
        conn.close()

@socketio.on('private_message')
def handle_private_message(data):
    username = session.get('username')
    recipient = data.get('to')
    message_text = data.get('text')

    if not username or not recipient or not message_text:
        emit('error', {'message': 'Ошибка: Вы не авторизованы или не указан получатель'})
        return

    recipient_sid = next((sid for sid, name in active_users.items() if name == recipient), None)

    # Если получатель подключен, отправляем ему сообщение
    if recipient_sid:
        emit('private_message', {'from': username, 'to': recipient, 'text': message_text}, room=recipient_sid)
    
    user_id = session.get('user_id')
    conn, cur = get_db()
    cur.execute("SELECT id FROM users WHERE username = %s", (recipient,))
    recipient_data = cur.fetchone()

    if recipient_data:
        recipient_id = recipient_data[0]
        cur.execute("INSERT INTO private_messages (user_id, recipient_id, message, is_read) VALUES (%s, %s, %s, FALSE)", 
                    (user_id, recipient_id, message_text))
        conn.commit()

        # Обновляем количество непрочитанных сообщений для получателя
        cur.execute("""
            SELECT COUNT(id) FROM private_messages
            WHERE recipient_id = %s AND is_read = FALSE
        """, (recipient_id,))
        unread_count = cur.fetchone()[0]

        if recipient_sid:
            emit('unread_counts', {recipient: unread_count}, room=recipient_sid)
    else:
        emit('error', {'message': 'Ошибка: Получатель не найден в базе данных'})

    cur.close()
    conn.close()

@socketio.on('private_file_upload_chunk')
def handle_private_file_upload_chunk(data):
    """Обрабатывает получение части файла для приватного чата."""
    file_name = data.get('file_name')
    file_data = data.get('file_data')
    chunk_index = data.get('chunk_index')
    total_chunks = data.get('total_chunks')
    recipient_username = data.get('to')
    sender_username = data.get('from')

    if not file_name or not file_data or not recipient_username:
        emit('error', {'message': 'Ошибка: данные файла отсутствуют или не указан получатель'})
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
        user_id = cur.fetchone()[0]
        cur.execute("SELECT id FROM users WHERE username = %s", (recipient_username,))
        recipient_id = cur.fetchone()[0]

        html_message = f"<a href='{file_url}' style='color: #0077ff;'>{file_name}</a>"

        try:
            # Сохраняем сообщение как HTML-ссылку в таблицу private_messages
            cur.execute("INSERT INTO private_messages (user_id, recipient_id, message) VALUES (%s, %s, %s)", 
                        (user_id, recipient_id, html_message))
            conn.commit()

            # Оповещаем получателя, если он в сети
            recipient_sid = next((sid for sid, name in active_users.items() if name == recipient_username), None)
            if recipient_sid:
                emit('private_message', {
                    'from': sender_username,
                    'to': recipient_username,
                    'text': html_message
                }, room=recipient_sid)
        except psycopg2.Error as e:
            conn.rollback()
            emit('error', {'message': 'Ошибка сохранения файла в базу данных'})
        finally:
            cur.close()
            conn.close()

@socketio.on('request_chat_history')
def handle_request_chat_history(data):
    chat_type = data.get('type')

    if chat_type == 'global':
        # Получаем историю общего чата
        chat_history = get_global_chat_history()
        
        # Форматируем сообщения для отправки клиенту, преобразуя timestamp в строку
        formatted_history = [{'sender': sender, 'text': message, 'timestamp': str(timestamp)} for sender, message, timestamp in chat_history]
        
        # Отправляем историю общего чата клиенту
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
            cur.close()
            conn.close()
            return

        recipient_id = recipient[0]
        user_id = session['user_id']

        # Получаем историю приватного чата
        chat_history = get_chat_history(user_id, recipient_id)
        formatted_history = [{'sender': sender, 'text': msg, 'timestamp': str(timestamp)} for msg, timestamp, sender in chat_history]

        # Отправляем историю приватного чата клиенту
        emit('chat_history', {'username': recipient_username, 'messages': formatted_history, 'type': 'private'}, room=request.sid)

        cur.close()
        conn.close()
    else:
        emit('error', {'message': 'Неверный тип чата: ' + chat_type})

@socketio.on('mark_messages_as_read')
def handle_mark_messages_as_read(data):
    recipient_username = session.get('username')
    sender_username = data.get('username')

    if not recipient_username or not sender_username:
        emit('error', {'message': 'Ошибка: Пользователь не найден'})
        return

    # Получение ID пользователей
    conn, cur = get_db()
    cur.execute("SELECT id FROM users WHERE username = %s", (sender_username,))
    sender = cur.fetchone()

    cur.execute("SELECT id FROM users WHERE username = %s", (recipient_username,))
    recipient = cur.fetchone()

    if not sender or not recipient:
        emit('error', {'message': 'Ошибка: Пользователь не найден'})
        cur.close()
        conn.close()
        return

    sender_id = sender[0]
    recipient_id = recipient[0]

    # Обновление статуса сообщений как прочитанных
    try:
        cur.execute("""
            UPDATE private_messages 
            SET is_read = TRUE 
            WHERE recipient_id = %s AND user_id = %s AND is_read = FALSE
        """, (recipient_id, sender_id))
        conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
        emit('error', {'message': 'Ошибка при обновлении статуса сообщений'})
    finally:
        cur.close()
        conn.close()

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
        user_id = cur.fetchone()[0]

        html_message = f"<a href='{file_url}' style='color: #0077ff;'>{file_name}</a>"

        try:
            # Сохраняем сообщение как HTML-ссылку в таблицу global_messages
            cur.execute("INSERT INTO global_messages (user_id, message) VALUES (%s, %s)", (user_id, html_message))
            conn.commit()

            # Оповещаем всех подключенных пользователей о новом файле
            emit('global_message', {
                'sender': sender_username,
                'text': html_message
            }, room='global_room')
        except psycopg2.Error as e:
            conn.rollback()
            emit('error', {'message': 'Ошибка сохранения сообщения в базу данных'})
        finally:
            cur.close()
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
    # Если sid передан явно, используем его, иначе используем request.sid
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