import os
import requests
from flask import Flask, request, jsonify
import yt_dlp
from flask_cors import CORS
from datetime import datetime
import logging
from instagrapi import Client
from instagrapi.exceptions import LoginRequired

# Configurar logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Cargar variables de entorno solo si estamos en desarrollo local
if os.environ.get('FLASK_ENV') != 'production':
    from dotenv import load_dotenv
    load_dotenv()

app = Flask(__name__)
CORS(app)

# Cargar credenciales de entorno
INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME')
INSTAGRAM_PASSWORD = os.getenv('INSTAGRAM_PASSWORD')
PROXY_URL = os.getenv('PROXY_URL')

def login_user():
    cl = Client()
    session_file = "session.json"

    login_via_session = False
    login_via_pw = False

    if os.path.exists(session_file):
        try:
            cl.load_settings(session_file)
            cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)

            # check if session is valid
            try:
                cl.get_timeline_feed()
            except LoginRequired:
                logger.info("Session is invalid, need to login via username and password")

                old_session = cl.get_settings()

                # use the same device uuids across logins
                cl.set_settings({})
                cl.set_uuids(old_session["uuids"])

                cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            login_via_session = True
        except Exception as e:
            logger.info("Couldn't login user using session information: %s" % e)

    if not login_via_session:
        try:
            logger.info("Attempting to login via username and password. username: %s" % INSTAGRAM_USERNAME)
            if cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD):
                login_via_pw = True
        except Exception as e:
            logger.info("Couldn't login user using username and password: %s" % e)

    if not login_via_pw and not login_via_session:
        raise Exception("Couldn't login user with either password or session")

    # Guardar la sesión
    cl.dump_settings(session_file)
    return cl

# Iniciar sesión con la API de Instagrapi
cl = login_user()
cl.set_proxy(PROXY_URL)

@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Bienvenido a la API de extracción de videos"}), 200

@app.route('/extract', methods=['POST'])
def extract_video_data():
    urls = request.json.get('urls')
    if not urls:
        return jsonify({'error': 'No se proporcionaron URLs'}), 400

    results = []

    for url in urls:
        try:
            if 'instagram.com' in url:
                result = extract_instagram_data(url)
            elif 'tiktok.com/t/' in url:
                resolved_url = resolve_tiktok_url(url)
                result = extract_using_ytdlp(resolved_url)
            else:
                result = extract_using_ytdlp(url)
            results.append(result)
        except Exception as e:
            logger.exception(f"Error al procesar URL: {url}")
            results.append({'url': url, 'error': str(e)})

    return jsonify(results), 200

def resolve_tiktok_url(url):
    try:
        response = requests.get(url, allow_redirects=True)
        return response.url
    except requests.RequestException as e:
        return url

def extract_using_ytdlp(url):
    scraperapi_key = os.getenv('SCRAPERAPI_KEY')
    proxy_url = f"http://scraperapi:{scraperapi_key}@proxy-server.scraperapi.com:8001"
    
    ydl_opts = {
        'skip_download': True,
        'proxy': proxy_url,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        if not info:
            raise Exception("No se pudo extraer la información del video")
        
        upload_date = info.get('upload_date')
        if upload_date:
            upload_date = datetime.strptime(upload_date, '%Y%m%d').strftime('%Y-%m-%d')
        
        return {
            'url': url,
            'title': info.get('title'),
            'duration': info.get('duration'),
            'view_count': info.get('view_count'),
            'like_count': info.get('like_count'),
            'upload_date': upload_date,
            'author': info.get('uploader'),
            'comments': info.get('comment_count'),
            'shares': info.get('repost_count')
        }
    except Exception as e:
        logger.exception(f"Error al extraer información de: {url}")
        return {'url': url, 'error': str(e)}

def extract_instagram_data(url):
    media_id = url.split('/')[-2]
    try:
        # Intentar primero con una solicitud pública
        try:
            media_info = cl.media_info_gql(media_id)
        except Exception as e:
            # Si falla, intentar con una solicitud privada
            media_info = cl.media_info_v1(media_id)
        
        return {
            'url': url,
            'author': media_info.user.username,
            'caption': media_info.caption_text,
            'likes': media_info.like_count,
            'comments': media_info.comment_count,
            'media_type': media_info.media_type,
        }
    except Exception as e:
        logger.exception(f"Error al extraer información de Instagram: {url}")
        return {'url': url, 'error': str(e)}

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
