import os
import requests
from flask import Flask, request, jsonify
import yt_dlp
from flask_cors import CORS
from datetime import datetime
import ssl
import certifi
import logging

# Configurar logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Cargar variables de entorno solo si estamos en desarrollo local
if os.environ.get('FLASK_ENV') != 'production':
    from dotenv import load_dotenv
    load_dotenv()

app = Flask(__name__)
CORS(app)

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
    
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    ydl_opts = {
        'skip_download': True,
        'proxy': proxy_url,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'quiet': False,
        'no_warnings': False,
        'format': 'best',
        'socket_timeout': 30,
        'retries': 3,
        'verbose': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl._opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url}),
                urllib.request.HTTPSHandler(context=ssl_context)
            )
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

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
