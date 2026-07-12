"""
YouTube Stream Extractor & Format Selector

Módulo responsável por:
- Extrair informações de vídeos (título, duração, formatos disponíveis)
- Resolver URLs diretas para streams de áudio/vídeo
- Ler manifestos de mídia adaptativa (DASH)
- Selecionar formatos e qualidades baseado em critérios
- Retornar URL de stream ou lista de opções
"""

import os
import time
import base64
import yt_dlp
import json
import logging
from typing import Dict, List, Optional, Tuple

_CACHE_TTL_SECONDS = 900
_VIDEO_INFO_CACHE: Dict[str, Dict] = {}


class YouTubeStreamExtractor:
    """Extrator de streams e metadados do YouTube."""

    def __init__(self):
        """Inicializa o extrator com configurações padronizadas."""
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 15,
        }
        # Cookie state tracking (path and validity)
        self._cookiefile_path: Optional[str] = None
        self._cookiefile_valid: bool = False

        # Logger for diagnostics (appears in Vercel logs)
        self._logger = logging.getLogger(__name__)
        if not logging.getLogger().handlers:
            # Ensure there is at least a basic handler so logs appear
            logging.basicConfig(level=logging.INFO)

    def _ensure_cookiefile(self) -> Optional[str]:
        # Reset state
        self._cookiefile_path = None
        self._cookiefile_valid = False

        cookies_path = os.environ.get('YTDLP_COOKIES_PATH')
        if cookies_path:
            # Respect explicit path, but validate if possible
            if os.path.exists(cookies_path):
                try:
                    with open(cookies_path, 'rb') as fd:
                        content = fd.read()
                    valid = self._validate_cookies_content(content)
                    self._cookiefile_path = cookies_path if valid else None
                    self._cookiefile_valid = valid
                    if not valid:
                        self._logger.warning('[cookies] Arquivo em YTDLP_COOKIES_PATH não parece um cookies.txt válido do YouTube — ignorando.')
                    return self._cookiefile_path
                except Exception as exc:
                    self._logger.warning('[cookies] Erro ao ler YTDLP_COOKIES_PATH: %s', exc)
                    return None
            return None

        b64 = os.environ.get('YTDLP_COOKIES_B64')
        if not b64:
            return None

        target_path = '/tmp/ytdlp_cookies.txt'
        # If file already exists, validate it before returning
        if os.path.exists(target_path):
            try:
                with open(target_path, 'rb') as fd:
                    content = fd.read()
                valid = self._validate_cookies_content(content)
                self._cookiefile_path = target_path if valid else None
                self._cookiefile_valid = valid
                if not valid:
                    self._logger.warning('[cookies] Arquivo em %s existe, mas não parece válido — ignorando.', target_path)
                return self._cookiefile_path
            except Exception as exc:
                self._logger.warning('[cookies] Erro ao ler %s: %s', target_path, exc)
                return None

        try:
            decoded = base64.b64decode(b64)
        except Exception as exc:
            self._logger.warning('[cookies] Falha ao decodificar YTDLP_COOKIES_B64: %s', exc)
            return None

        # Validate before writing
        if not self._validate_cookies_content(decoded):
            self._logger.warning('[cookies] Arquivo em YTDLP_COOKIES_B64 não parece um cookies.txt válido do YouTube — ignorando.')
            return None

        try:
            with open(target_path, 'wb') as fd:
                fd.write(decoded)
            self._cookiefile_path = target_path
            self._cookiefile_valid = True
            try:
                size = os.path.getsize(target_path)
            except Exception:
                size = None
            self._logger.info('[cookies] Escreveu %s com %s bytes (validação OK).', target_path, size)
            return target_path
        except Exception as exc:
            self._logger.warning('[cookies] Erro ao escrever %s: %s', target_path, exc)
            return None

    def _validate_cookies_content(self, content: bytes) -> bool:
        """Valida de forma simples se bytes representam um cookies.txt do Netscape/yt-dlp.

        Regras básicas:
        - Começa com header conhecido (# Netscape HTTP Cookie File ou # HTTP Cookie File)
          OR contém linhas com 7 campos separados por tab.
        - Contém ao menos uma linha com 'youtube.com' ou '.youtube.com'.
        """
        if not content:
            return False
        try:
            text = content.decode('utf-8', errors='replace')
        except Exception:
            return False

        stripped = text.lstrip()
        has_header = stripped.startswith('# Netscape HTTP Cookie File') or stripped.startswith('# HTTP Cookie File')

        lines = [ln for ln in text.splitlines() if ln and not ln.strip().startswith('#')]
        has_seven_field = False
        has_youtube = False
        for ln in lines:
            if 'youtube.com' in ln:
                has_youtube = True
            parts = ln.split('\t')
            if len(parts) >= 7:
                has_seven_field = True

        return (has_header or has_seven_field) and has_youtube

    def _build_options(self, extra: Optional[Dict] = None) -> Dict:
        opts = {
            **self.ydl_opts,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            'geo_bypass': True,
            'nocheckcertificate': True,
            'source_address': '0.0.0.0',
            'retries': 3,
            'cachedir': '/tmp/ytdlp_cache',
            'nopart': True,
        }

        cookiefile = self._ensure_cookiefile()
        if cookiefile and self._cookiefile_valid:
            opts['cookiefile'] = cookiefile
        else:
            # Fallback to cookies_from_browser only if set; do not fabricate cookies
            cookies_browser = os.environ.get('YTDLP_COOKIES_FROM_BROWSER')
            if cookies_browser:
                opts['cookies_from_browser'] = cookies_browser

        proxy = os.environ.get('YTDLP_PROXY')
        if proxy:
            opts['proxy'] = proxy

        if extra:
            # Preserve extractor_args if passed explicitly
            extractor_args = extra.pop('extractor_args', None)
            if extractor_args:
                opts['extractor_args'] = extractor_args
            opts.update(extra)

        return opts

    def _run_ydl(self, url: str, extra: Optional[Dict] = None) -> Dict:
        ydl_opts = self._build_options(extra)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    def extract_video_info(self, url: str) -> Dict:
        """
        Extrai informações de vídeo: título, duração, formatos disponíveis.

        Args:
            url: URL do YouTube (youtube.com, youtu.be, etc)

        Returns:
            Dicionário com metadados ou erro informado
        """
        cache_key = url.strip()
        now = time.time()
        cached = _VIDEO_INFO_CACHE.get(cache_key)
        if cached and cached['expires'] > now:
            return cached['value']

        # Diagnostic logs about cookie env and status
        has_env = bool(os.environ.get('YTDLP_COOKIES_B64') or os.environ.get('YTDLP_COOKIES_PATH'))
        # Ensure we have evaluated cookiefile path/validity
        _ = self._ensure_cookiefile()
        cookie_path = self._cookiefile_path
        cookie_valid = self._cookiefile_valid
        cookie_size = None
        if cookie_path and cookie_valid:
            try:
                cookie_size = os.path.getsize(cookie_path)
            except Exception:
                cookie_size = None
        self._logger.info('[cookies] YTDLP_COOKIES_B64 definida: %s; cookiefile: %s; tamanho_bytes: %s; validacao: %s',
                          has_env, bool(cookie_path), cookie_size, cookie_valid)

        client_strategies = [None, 'android', 'ios', 'web_creator']
        errors = []
        info = None
        for client in client_strategies:
            extra = {}
            if client:
                extra['extractor_args'] = {'youtube': {'player_client': [client]}}
            try:
                info = self._run_ydl(url, extra)
                break
            except Exception as exc:
                errors.append((client or 'default', str(exc)))
                continue

        if not info:
            error_text = errors[-1][1] if errors else 'Falha desconhecida ao extrair o vídeo.'
            readable_error = error_text.lower()
            # Heurística de bot-check/cookies
            bot_signals = ['sign in to confirm', 'cookies', 'botguard', 'po token', 'verify you are human']
            if any(s in readable_error for s in bot_signals):
                # Differentiate whether we had valid cookies loaded
                if cookie_path and cookie_valid:
                    # Cookies were provided and structurally valid — likely expired/flagged
                    self._logger.warning('[cookies] Detected bot-check while cookies valid: %s', readable_error)
                    return {'error': 'Os cookies do YouTube parecem inválidos ou expiraram. Atualize YTDLP_COOKIES_B64 no Vercel.'}
                else:
                    # No cookies configured or invalid cookies — inform maintenance logs
                    self._logger.warning('[cookies] Detected bot-check without valid cookies: %s', readable_error)
                    return {'error': 'Este vídeo está temporariamente indisponível para download automático. Tente novamente em alguns minutos ou use outro vídeo.'}

            # Other errors: log full error types (without sensitive data)
            self._logger.info('[yt-dlp] extraction errors: %s', errors)
            return {'error': 'Este vídeo está temporariamente indisponível para download automático. Tente novamente em alguns minutos ou use outro vídeo.'}

        result = {
            'id': info.get('id'),
            'title': info.get('title', 'Vídeo'),
            'duration': info.get('duration', 0),
            'uploader': info.get('uploader', 'Desconhecido'),
            'formats': self._extract_formats(info),
        }
        _VIDEO_INFO_CACHE[cache_key] = {'expires': now + _CACHE_TTL_SECONDS, 'value': result}
        return result

    def _extract_formats(self, info: Dict) -> List[Dict]:
        """
        Extrai lista de formatos disponíveis com resoluções e codecs.

        Prioriza:
        - MP3: audio/mp3 em alta qualidade
        - MP4: video+audio em qualidades (1080p, 720p, 480p)
        """
        formats = []

        # Extrair streams de áudio (para MP3)
        audio_formats = [
            f for f in info.get('formats', [])
            if f.get('vcodec') == 'none' and f.get('acodec') != 'none'
        ]
        if audio_formats:
            best_audio = max(audio_formats, key=lambda x: x.get('abr', 0) or 0)
            formats.append({
                'format_id': best_audio['format_id'],
                'ext': 'mp3',
                'type': 'audio',
                'quality': f"{best_audio.get('abr', 128)}kbps",
                'format_note': best_audio.get('format_note', 'Áudio'),
                'filesize': best_audio.get('filesize'),
            })

        # Extrair streams de vídeo (para MP4)
        video_formats = [
            f for f in info.get('formats', [])
            if f.get('vcodec') != 'none' and f.get('acodec') == 'none'
        ]
        
        resolution_map = {}
        for fmt in video_formats:
            height = fmt.get('height', 0)
            if height > 0:
                if height not in resolution_map or \
                   fmt.get('vbr', 0) > resolution_map[height].get('vbr', 0):
                    resolution_map[height] = fmt

        for height in sorted(resolution_map.keys(), reverse=True):
            fmt = resolution_map[height]
            formats.append({
                'format_id': fmt['format_id'],
                'ext': 'mp4',
                'type': 'video',
                'quality': f"{fmt.get('height')}p",
                'format_note': fmt.get('format_note', f"{fmt.get('height')}p"),
                'filesize': fmt.get('filesize'),
            })

        return formats

    def get_stream_url(self, url: str, format_id: str) -> Optional[str]:
        """
        Retorna a URL direta de stream para um format_id específico.

        Args:
            url: URL do YouTube
            format_id: ID do formato (ex: "251", "18", etc)

        Returns:
            URL de stream ou None
        """
        try:
            info = self._run_ydl(url, {'format': format_id})
            if info.get('url'):
                return info['url']
            for fmt in info.get('formats', []):
                if fmt.get('format_id') == format_id and fmt.get('url'):
                    return fmt['url']
        except Exception:
            pass
        return None

    def get_best_audio_stream(self, url: str) -> Optional[Tuple[str, str]]:
        """
        Retorna a melhor stream de áudio (para MP3).

        Returns:
            Tupla (url_stream, título) ou None
        """
        try:
            ydl_opts = {**self.ydl_opts, 'format': 'bestaudio/best'}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'url' in info:
                    title = info.get('title', 'audio').replace('/', '_')
                    return (info['url'], f"{title}.mp3")
        except Exception:
            pass
        return None

    def get_best_video_stream(self, url: str) -> Optional[Tuple[str, str]]:
        """
        Retorna a melhor stream de vídeo (para MP4).

        Returns:
            Tupla (url_stream, título) ou None
        """
        try:
            ydl_opts = {**self.ydl_opts, 'format': 'best[ext=mp4]/best'}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'url' in info:
                    title = info.get('title', 'video').replace('/', '_')
                    return (info['url'], f"{title}.mp4")
        except Exception:
            pass
        return None


# Singleton global
_extractor = None


def get_extractor() -> YouTubeStreamExtractor:
    """Retorna instância singleton do extrator."""
    global _extractor
    if not _extractor:
        _extractor = YouTubeStreamExtractor()
    return _extractor
