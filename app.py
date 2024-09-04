import os
import requests
from flask import Flask, request, jsonify
import yt_dlp
from flask_cors import CORS
from datetime import datetime
import logging
import instaloader

# Configurar logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Cargar variables de entorno solo si estamos en desarrollo local
if os.environ.get('FLASK_ENV') != 'production':
    from dotenv import load_dotenv
    load_dotenv()

app = Flask(__name__)
CORS(app)

# Autenticación de Instaloader
INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME')
INSTAGRAM_PASSWORD = os.getenv('INSTAGRAM_PASSWORD')

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
            if 'tiktok.com/t/' in url:
                resolved_url = resolve_tiktok_url(url)
            elif 'instagram.com' in url:
                result = extract_using_instaloader(url)
            else:
                resolved_url = url
                result = extract_using_ytdlp(resolved_url)
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

def extract_using_instaloader(url):
    L = instaloader.Instaloader()
    
    # Autenticarse si las credenciales están disponibles
    if INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD:
        try:
            L.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
        except Exception as e:
            logger.exception("Error al iniciar sesión en Instagram")
            return {'url': url, 'error': 'Error al iniciar sesión en Instagram'}

    post_shortcode = url.split("/")[-2]
    
    try:
        post = instaloader.Post.from_shortcode(L.context, post_shortcode)
        
        return {
            'url': url,
            'title': post.title,
            'upload_date': post.date.strftime('%Y-%m-%d'),
            'author': post.owner_username,
            'likes': post.likes,
            'comments': post.comments,
            'is_video': post.is_video,
            'video_url': post.video_url if post.is_video else None,
            'image_url': post.url if not post.is_video else None
        }
    except Exception as e:
        logger.exception(f"Error al extraer información de Instagram: {url}")
        return {'url': url, 'error': str(e)}

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
