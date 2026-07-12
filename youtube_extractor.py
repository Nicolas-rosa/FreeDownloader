"""Extração de metadados e streams do YouTube com fallback de autenticação."""

import base64
import logging
import os
import time
from copy import deepcopy
from typing import Dict, Iterator, List, Literal, Optional, Tuple
from urllib.parse import urlsplit

import yt_dlp


AuthStrategy = Literal['pot', 'cookies', 'client_spoof']
_CACHE_TTL_SECONDS = 900
_VIDEO_INFO_CACHE: Dict[str, Dict] = {}
_BOT_SIGNALS = ('sign in to confirm', 'cookies', 'botguard', 'po token', 'verify you are human')
_SPOOF_CLIENTS = (None, 'android', 'ios', 'web_creator')


class YouTubeStreamExtractor:
    """Extrai informações e streams, sem depender de cookies quando há POT."""

    def __init__(self):
        self._logger = logging.getLogger(__name__)
        if not logging.getLogger().handlers:
            logging.basicConfig(level=logging.INFO)

        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 15,
            'geo_bypass': True,
            'nocheckcertificate': True,
            'source_address': '0.0.0.0',
            'retries': 3,
            'cachedir': '/tmp/ytdlp_cache',
            'nopart': True,
            'http_headers': {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                ),
                'Accept-Language': 'en-US,en;q=0.9',
            },
        }

        self._cookie_path: Optional[str] = None
        self._cookies_loaded = False
        self._cookies: List[Tuple[int, str]] = []
        self._cookie_index = 0

        # Carrega cookie do YouTube via YTDLP_COOKIES_B64
        cookie_b64 = os.environ.get('YTDLP_COOKIES_B64')
        if cookie_b64:
            self._logger.info('[cookies] YTDLP_COOKIES_B64 encontrada.')
            try:
                cookie_content = base64.b64decode(cookie_b64, validate=True)
                if self._valid_cookie_content(cookie_content):
                    cookie_path = '/tmp/cookies.txt'
                    if not os.path.exists(cookie_path):
                        with open(cookie_path, 'wb') as f:
                            f.write(cookie_content)
                        os.chmod(cookie_path, 0o600)
                    self._cookie_path = cookie_path
                    self.ydl_opts['cookiefile'] = cookie_path
                    self._logger.info('[cookies] Arquivo validado com sucesso (%d bytes).', len(cookie_content))
                else:
                    self._logger.warning('[cookies] YTDLP_COOKIES_B64 ignorada: conteúdo inválido.')
            except (ValueError, OSError) as exc:
                self._logger.warning('[cookies] YTDLP_COOKIES_B64 ignorada: %s', exc)

        self._pot_provider_url = os.environ.get('YTDLP_POT_PROVIDER_URL', '').strip() or None
        self._pot_provider_secret = os.environ.get('YTDLP_POT_PROVIDER_SECRET', '') or None
        self._pot_provider_class = self._load_pot_plugin() if self._pot_provider_url else None
        self._pot_available = bool(self._pot_provider_url and self._pot_provider_class)

        if self._pot_available and self._pot_provider_secret:
            self._install_pot_secret_adapter()

        if self._pot_available:
            self._logger.info('[pot] Provider configurado em %s.', self._pot_provider_label())
        elif self._pot_provider_url:
            self._logger.error('[pot] Provider configurado, mas o plugin bgutil-ytdlp-pot-provider não está instalado.')
        else:
            self._logger.info('[auth] POT não configurado; cookies e client spoof ficam como fallback.')

    def _load_pot_plugin(self):
        try:
            from yt_dlp_plugins.extractor.getpot_bgutil_http import BgUtilHTTPPTP
            return BgUtilHTTPPTP
        except ImportError:
            return None

    def _pot_provider_label(self) -> str:
        """Nome seguro para logs: nunca inclui credenciais, query ou fragmento."""
        if not self._pot_provider_url:
            return 'não configurado'
        parsed = urlsplit(self._pot_provider_url)
        if not (parsed.scheme and parsed.hostname):
            return 'URL configurada'
        try:
            suffix = f':{parsed.port}' if parsed.port else ''
        except ValueError:
            return 'URL configurada'
        return f'{parsed.scheme}://{parsed.hostname}{suffix}'

    def _install_pot_secret_adapter(self) -> None:
        """Inclui o segredo apenas nas duas chamadas HTTP do provider bgutil."""
        provider_class = self._pot_provider_class
        if getattr(provider_class, '_freedownloader_secret_adapter_installed', False):
            return

        original_request_webpage = provider_class._request_webpage
        provider_base_url = self._pot_provider_url.rstrip('/')
        provider_secret = self._pot_provider_secret

        def authenticated_request_webpage(provider, request, *args, **kwargs):
            if getattr(request, 'url', '').startswith(f'{provider_base_url}/'):
                request.headers['X-PO-Token-Auth'] = provider_secret
            return original_request_webpage(provider, request, *args, **kwargs)

        provider_class._request_webpage = authenticated_request_webpage
        provider_class._freedownloader_secret_adapter_installed = True
        self._logger.info('[pot] Autenticação por header do provider habilitada.')

    @staticmethod
    def _valid_cookie_content(content: bytes) -> bool:
        if not content:
            return False
        text = content.decode('utf-8', errors='replace')
        lines = [line for line in text.splitlines() if line and not line.startswith('#')]
        has_header = text.lstrip().startswith(('# Netscape HTTP Cookie File', '# HTTP Cookie File'))
        has_cookie_row = any(len(line.split('\t')) >= 7 for line in lines)
        return (has_header or has_cookie_row) and any('youtube.com' in line for line in lines)

    def _load_cookies(self) -> List[Tuple[int, str]]:
        if self._cookies_loaded:
            return self._cookies

        entries = []
        legacy = os.environ.get('YTDLP_COOKIES_B64')
        if legacy:
            entries.append((1, legacy, 'YTDLP_COOKIES_B64'))
        for account in range(1, 101):
            name = f'YTDLP_COOKIES_B64_{account}'
            value = os.environ.get(name)
            if not value:
                break
            entries.append((account, value, name))

        for account, encoded, name in entries:
            try:
                content = base64.b64decode(encoded, validate=True)
                if not self._valid_cookie_content(content):
                    self._logger.warning('[cookies] %s ignorado: conteúdo inválido.', name)
                    continue
                path = f'/tmp/ytdlp_cookies_{account}.txt'
                with open(path, 'wb') as cookie_file:
                    cookie_file.write(content)
                os.chmod(path, 0o600)
                self._cookies.append((account, path))
            except (ValueError, OSError) as exc:
                self._logger.warning('[cookies] %s ignorado: %s', name, exc)

        self._cookies_loaded = True
        self._logger.info('[cookies] %d conta(s) válida(s) carregada(s).', len(self._cookies))
        return self._cookies

    def _next_cookie(self) -> Optional[str]:
        cookies = self._load_cookies()
        if not cookies:
            return None
        _, path = cookies[self._cookie_index % len(cookies)]
        self._cookie_index += 1
        return path if os.path.exists(path) else None

    def _cookie_options(self, rotate: bool) -> Dict:
        options = {}
        cookie_path = self._next_cookie() if rotate else None
        if not cookie_path:
            path_from_env = os.environ.get('YTDLP_COOKIES_PATH')
            if path_from_env and os.path.isfile(path_from_env):
                cookie_path = path_from_env
        if cookie_path:
            options['cookiefile'] = cookie_path
        elif browser := os.environ.get('YTDLP_COOKIES_FROM_BROWSER'):
            options['cookies_from_browser'] = browser
        return options

    def _build_options(
        self,
        extra: Optional[Dict] = None,
        strategy: AuthStrategy = 'client_spoof',
        rotate_cookie: bool = False,
    ) -> Dict:
        options = deepcopy(self.ydl_opts)
        extra = deepcopy(extra) if extra else {}

        if strategy == 'pot':
            extra.setdefault('extractor_args', {}).setdefault(
                'youtubepot-bgutilhttp', {}
            )['base_url'] = [self._pot_provider_url]
        elif strategy == 'cookies':
            options.update(self._cookie_options(rotate_cookie))

        if proxy := os.environ.get('YTDLP_PROXY'):
            options['proxy'] = proxy
        options.update(extra)
        return options

    def _attempts(self) -> Iterator[Tuple[AuthStrategy, Optional[str], bool]]:
        """POT primeiro; cookies são apenas fallback; spoof sempre encerra a cadeia."""
        if self._pot_available:
            yield 'pot', None, False

        cookies = self._load_cookies()
        if cookies:
            for _ in cookies:
                yield 'cookies', None, True
        elif os.environ.get('YTDLP_COOKIES_PATH') or os.environ.get('YTDLP_COOKIES_FROM_BROWSER'):
            yield 'cookies', None, False

        for client in _SPOOF_CLIENTS:
            yield 'client_spoof', client, False

    def _extract_with_fallback(self, url: str, extra: Optional[Dict] = None) -> Dict:
        errors = []
        for strategy, client, rotate_cookie in self._attempts():
            attempt_extra = deepcopy(extra) if extra else {}
            if client:
                attempt_extra.setdefault('extractor_args', {}).setdefault('youtube', {})['player_client'] = [client]
            self._logger.info('[auth] Tentativa: %s%s', strategy, f' ({client})' if client else '')
            try:
                options = self._build_options(attempt_extra, strategy, rotate_cookie)
                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.extract_info(url, download=False)
            except Exception as exc:
                message = str(exc).lower()
                errors.append(message)
                kind = 'bot-check' if any(signal in message for signal in _BOT_SIGNALS) else 'erro'
                self._logger.warning('[auth] %s falhou (%s); tentando fallback.', strategy, kind)

        raise RuntimeError(errors[-1] if errors else 'Falha ao extrair o vídeo.')

    def extract_video_info(self, url: str) -> Dict:
        cache_key = url.strip()
        cached = _VIDEO_INFO_CACHE.get(cache_key)
        if cached and cached['expires'] > time.time():
            return cached['value']

        try:
            info = self._extract_with_fallback(url)
        except Exception as exc:
            self._logger.warning('[youtube] Extração falhou após todos os fallbacks: %s', str(exc)[:160])
            return {'error': 'Não foi possível acessar este vídeo agora. Tente novamente mais tarde.'}

        result = {
            'id': info.get('id'),
            'title': info.get('title', 'Vídeo'),
            'duration': info.get('duration', 0),
            'uploader': info.get('uploader', 'Desconhecido'),
            'formats': self._extract_formats(info),
        }
        _VIDEO_INFO_CACHE[cache_key] = {'expires': time.time() + _CACHE_TTL_SECONDS, 'value': result}
        return result

    @staticmethod
    def _extract_formats(info: Dict) -> List[Dict]:
        formats = []
        audio_formats = [
            item for item in info.get('formats', [])
            if item.get('vcodec') == 'none' and item.get('acodec') != 'none'
        ]
        if audio_formats:
            best_audio = max(audio_formats, key=lambda item: item.get('abr', 0) or 0)
            formats.append({
                'format_id': best_audio['format_id'], 'ext': 'mp3', 'type': 'audio',
                'quality': f"{best_audio.get('abr', 128)}kbps",
                'format_note': best_audio.get('format_note', 'Áudio'),
                'filesize': best_audio.get('filesize'),
            })

        best_by_height = {}
        for item in info.get('formats', []):
            if item.get('vcodec') == 'none' or item.get('acodec') != 'none':
                continue
            height = item.get('height') or 0
            if height and (height not in best_by_height or (item.get('vbr') or 0) > (best_by_height[height].get('vbr') or 0)):
                best_by_height[height] = item
        for height in sorted(best_by_height, reverse=True):
            item = best_by_height[height]
            formats.append({
                'format_id': item['format_id'], 'ext': 'mp4', 'type': 'video',
                'quality': f'{height}p', 'format_note': item.get('format_note', f'{height}p'),
                'filesize': item.get('filesize'),
            })
        return formats

    @staticmethod
    def _safe_stream_headers(headers: Optional[Dict]) -> Dict[str, str]:
        return {
            str(key): str(value)
            for key, value in (headers or {}).items()
            if str(key).lower() not in {'cookie', 'authorization', 'x-po-token-auth'}
        }

    def get_stream(self, url: str, format_id: str) -> Optional[Dict[str, object]]:
        try:
            info = self._extract_with_fallback(url, {'format': format_id})
        except Exception as exc:
            self._logger.warning('[youtube] Stream indisponível: %s', str(exc)[:160])
            return None

        selected = next((item for item in info.get('formats', []) if item.get('format_id') == format_id), info)
        stream_url = selected.get('url') or info.get('url')
        if not stream_url:
            return None
        return {'url': stream_url, 'headers': self._safe_stream_headers(selected.get('http_headers') or info.get('http_headers'))}

    def get_stream_url(self, url: str, format_id: str) -> Optional[str]:
        stream = self.get_stream(url, format_id)
        return stream['url'] if stream else None

    def get_best_audio_stream(self, url: str) -> Optional[Tuple[str, str]]:
        stream = self.get_stream(url, 'bestaudio/best')
        if not stream:
            return None
        info = self.extract_video_info(url)
        title = info.get('title', 'audio').replace('/', '_') if not info.get('error') else 'audio'
        return stream['url'], f'{title}.mp3'

    def get_best_video_stream(self, url: str) -> Optional[Tuple[str, str]]:
        stream = self.get_stream(url, 'best[ext=mp4]/best')
        if not stream:
            return None
        info = self.extract_video_info(url)
        title = info.get('title', 'video').replace('/', '_') if not info.get('error') else 'video'
        return stream['url'], f'{title}.mp4'


_extractor: Optional[YouTubeStreamExtractor] = None


def get_extractor() -> YouTubeStreamExtractor:
    global _extractor
    if _extractor is None:
        _extractor = YouTubeStreamExtractor()
    return _extractor
