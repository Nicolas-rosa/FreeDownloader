from flask import Flask, render_template, request, Response, redirect, url_for, flash, jsonify
from pathlib import PurePosixPath
from ipaddress import ip_address
from socket import getaddrinfo
from os import environ
import requests
from urllib.parse import urlparse
from youtube_extractor import get_extractor

app = Flask(__name__)
app.secret_key = environ.get("SECRET_KEY", "change-me-in-production")
app.config["SUPPORT_EMAIL"] = environ.get("SUPPORT_EMAIL", "nicolasfrancacastrorosa@gmail.com")

# Configuration
ALLOWED_MIME = {"audio/mpeg", "audio/mp3", "video/mp4", "audio/mp4"}
MAX_SIZE_BYTES = 200 * 1024 * 1024  # 200 MB max
PLATFORM_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def is_allowed_url(parsed):
    """Accept only public HTTP(S) hosts to avoid fetching internal resources."""
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        addresses = {item[4][0] for item in getaddrinfo(parsed.hostname, None)}
        return bool(addresses) and all(not ip_address(address).is_private
                                   and not ip_address(address).is_loopback
                                   and not ip_address(address).is_link_local
                                   and not ip_address(address).is_reserved
                                   for address in addresses)
    except (OSError, ValueError):
        return False


def guess_filename_from_url(url):
    name = PurePosixPath(urlparse(url).path).name or "arquivo"
    # Avoid a header-injection vector and provide a sensible extension fallback.
    name = "".join(char for char in name if char.isalnum() or char in ".-_ ")[:120]
    return name or "arquivo"


def is_platform_page(parsed):
    host = (parsed.hostname or "").lower()
    return host in PLATFORM_HOSTS or host.endswith(".youtube.com")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url', '').strip()
    confirm = request.form.get('confirm')

    if not url:
        flash('Por favor informe uma URL válida.', 'danger')
        return redirect(url_for('index'))

    if confirm != 'on':
        flash('Você deve confirmar que possui os direitos sobre o arquivo.', 'warning')
        return redirect(url_for('index'))

    parsed = urlparse(url)
    if not is_allowed_url(parsed):
        flash('Apenas URLs http(s) são aceitas.', 'danger')
        return redirect(url_for('index'))

    if is_platform_page(parsed):
        flash('Este é um link de página do YouTube, e não uma URL direta de arquivo. Para baixar um vídeo seu, use a opção de download no YouTube Studio; aqui, cole apenas o link direto para um MP3 ou MP4 hospedado por você.', 'warning')
        return redirect(url_for('index'))

    # Inspect the resource before streaming it.
    try:
        head = requests.head(url, allow_redirects=True, timeout=10)
        head.raise_for_status()
        final_url = head.url
    except requests.RequestException:
        flash('Não foi possível acessar a URL. Verifique e tente novamente.', 'danger')
        return redirect(url_for('index'))

    if not is_allowed_url(urlparse(final_url)):
        flash('A URL de destino não é permitida.', 'danger')
        return redirect(url_for('index'))

    ctype = head.headers.get('Content-Type', '').split(';')[0]
    clen = head.headers.get('Content-Length')

    if ctype not in ALLOWED_MIME:
        flash('Somente arquivos nos formatos MP3 e MP4 são permitidos.', 'danger')
        return redirect(url_for('index'))

    if clen:
        try:
            if int(clen) > MAX_SIZE_BYTES:
                flash('Arquivo muito grande. Limite: 200MB.', 'danger')
                return redirect(url_for('index'))
        except ValueError:
            pass

    # Stream the file back to the user
    try:
        r = requests.get(final_url, stream=True, allow_redirects=False, timeout=(5, 30))
        r.raise_for_status()
    except requests.RequestException:
        flash('Erro ao baixar o arquivo.', 'danger')
        return redirect(url_for('index'))

    def generate():
        downloaded = 0
        try:
            for chunk in r.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                downloaded += len(chunk)
                if downloaded > MAX_SIZE_BYTES:
                    break
                yield chunk
        finally:
            r.close()

    filename = guess_filename_from_url(final_url)
    headers = {
        'Content-Type': ctype,
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    return Response(generate(), headers=headers)


@app.route('/terms')
def terms():
    return render_template('terms.html')


@app.route('/privacy')
def privacy():
    return render_template('privacy.html')


@app.route('/contacts')
def contacts():
    return render_template('contacts.html')


@app.route('/dmca')
def dmca():
    return render_template('dmca.html')


@app.route('/extract-youtube', methods=['POST'])
def extract_youtube():
    """
    Extrai informações de vídeo do YouTube e retorna formatos disponíveis.
    Endpoint JSON para suportar seleção de qualidade.

    Request (POST):
        url: URL do YouTube

    Response (JSON):
        {
            "success": true/false,
            "message": str,
            "video_info": {
                "id": str,
                "title": str,
                "duration": int (segundos),
                "uploader": str,
                "formats": [
                    {
                        "format_id": str,
                        "ext": "mp3" | "mp4",
                        "type": "audio" | "video",
                        "quality": str,
                        "filesize": int | null
                    }
                ]
            }
        }
    """
    url = request.form.get('url', '').strip()

    if not url:
        return jsonify({'success': False, 'message': 'URL é obrigatória'}), 400

    parsed = urlparse(url)
    if not is_platform_page(parsed):
        return jsonify({
            'success': False,
            'message': 'Apenas URLs do YouTube são aceitas neste endpoint. Use /download para URLs diretas.'
        }), 400

    extractor = get_extractor()
    info = extractor.extract_video_info(url)

    if not info or info.get('error'):
        message = info.get('error') if info else 'Não foi possível extrair informações do vídeo. Verifique a URL.'
        if 'autenticação' in message.lower() or 'cookies' in message.lower():
            message = (
                'Este vídeo requer autenticação ou cookies do YouTube. ' 
                'No ambiente Vercel, você precisa definir YTDLP_COOKIES_PATH ou usar outro vídeo.'
            )
        return jsonify({
            'success': False,
            'message': message
        }), 400

    return jsonify({
        'success': True,
        'video_info': {
            'id': info['id'],
            'title': info['title'],
            'duration': info['duration'],
            'uploader': info.get('uploader', 'Desconhecido'),
            'formats': info['formats']
        }
    })


@app.route('/download-youtube', methods=['POST'])
def download_youtube():
    """
    Baixa e converte stream do YouTube em MP3 ou MP4.

    Request (POST):
        url: URL do YouTube
        format_id: ID do formato extraído
        type: 'audio' para MP3 ou 'video' para MP4

    Response:
        Stream de arquivo ou redirecionamento com mensagem de erro
    """
    url = request.form.get('url', '').strip()
    format_id = request.form.get('format_id', '').strip()
    fmt_type = request.form.get('type', '').strip()
    confirm = request.form.get('confirm')

    if not url or not format_id or not fmt_type:
        flash('URL, formato e tipo são obrigatórios.', 'danger')
        return redirect(url_for('index'))

    if fmt_type not in ('audio', 'video'):
        flash('Tipo inválido. Use "audio" ou "video".', 'danger')
        return redirect(url_for('index'))

    if confirm != 'on':
        flash('Você deve confirmar que possui os direitos sobre este vídeo.', 'warning')
        return redirect(url_for('index'))

    parsed = urlparse(url)
    if not is_platform_page(parsed):
        flash('Apenas URLs do YouTube são aceitas.', 'danger')
        return redirect(url_for('index'))

    extractor = get_extractor()

    # Extrair stream URL
    stream_url = extractor.get_stream_url(url, format_id)
    if not stream_url:
        flash('Não foi possível obter o stream do vídeo. Tente novamente.', 'danger')
        return redirect(url_for('index'))

    # Validar stream URL
    try:
        head = requests.head(stream_url, allow_redirects=True, timeout=10)
        head.raise_for_status()
    except requests.RequestException:
        flash('O stream do vídeo não está mais disponível.', 'danger')
        return redirect(url_for('index'))

    # Verificar tamanho
    clen = head.headers.get('Content-Length')
    if clen:
        try:
            if int(clen) > MAX_SIZE_BYTES:
                flash('O vídeo é muito grande. Limite: 200MB.', 'danger')
                return redirect(url_for('index'))
        except ValueError:
            pass

    # Fazer download do stream
    try:
        r = requests.get(stream_url, stream=True, allow_redirects=False, timeout=(5, 30))
        r.raise_for_status()
    except requests.RequestException:
        flash('Erro ao baixar o stream do vídeo.', 'danger')
        return redirect(url_for('index'))

    def generate():
        downloaded = 0
        try:
            for chunk in r.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                downloaded += len(chunk)
                if downloaded > MAX_SIZE_BYTES:
                    break
                yield chunk
        finally:
            r.close()

    # Gerar nome de arquivo sanitizado
    info = extractor.extract_video_info(url)
    if info:
        filename = info['title'][:100].replace('/', '_')
    else:
        filename = 'video'

    ext = 'mp3' if fmt_type == 'audio' else 'mp4'
    filename = f"{filename}.{ext}"

    # Definir headers adequados
    content_type = 'audio/mpeg' if fmt_type == 'audio' else 'video/mp4'
    headers = {
        'Content-Type': content_type,
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    return Response(generate(), headers=headers)


if __name__ == '__main__':
    app.run(debug=environ.get("FLASK_DEBUG") == "1", host='0.0.0.0')
