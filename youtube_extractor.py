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
import random
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
        
        # Multi-account cookie rotation
        self._valid_cookies_list: List[Tuple[int, str, bool]] = []  # [(account_number, path, is_valid), ...]
        self._cookie_round_robin_index: int = 0
        self._cookies_loaded: bool = False

        # Logger for diagnostics (appears in Vercel logs)
        self._logger = logging.getLogger(__name__)
        if not logging.getLogger().handlers:
            # Ensure there is at least a basic handler so logs appear
            logging.basicConfig(level=logging.INFO)

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

    def _load_all_cookies(self) -> List[Tuple[int, str, bool]]:
        """Carrega todos os cookies disponíveis nas env vars.
        
        Busca por:
        - YTDLP_COOKIES_B64 (sem número) → account 1 (compat. legado)
        - YTDLP_COOKIES_B64_1, _2, _3, ..., _N
        
        Retorna lista de (account_number, cookie_file_path, is_valid)
        """
        if self._cookies_loaded:
            return self._valid_cookies_list

        valid_cookies = []

        # Check for legacy YTDLP_COOKIES_B64 (without number) → account 1
        legacy_b64 = os.environ.get('YTDLP_COOKIES_B64')
        if legacy_b64:
            account_idx = 1
            try:
                decoded = base64.b64decode(legacy_b64)
                is_valid = self._validate_cookies_content(decoded)
                target_path = f'/tmp/ytdlp_cookies_{account_idx}.txt'
                if is_valid:
                    with open(target_path, 'wb') as fd:
                        fd.write(decoded)
                    valid_cookies.append((account_idx, target_path, True))
                    self._logger.info('[cookies] Conta %d carregada e validada com sucesso (%d bytes).', account_idx, len(decoded))
                else:
                    self._logger.warning('[cookies] Conta %d rejeitada: conteúdo em YTDLP_COOKIES_B64 não é um cookies.txt válido.', account_idx)
            except Exception as exc:
                self._logger.warning('[cookies] Erro ao processar YTDLP_COOKIES_B64 (conta 1): %s', exc)

        # Check for numbered env vars YTDLP_COOKIES_B64_1, _2, _3, ..., _N
        account_idx = 1
        while True:
            env_var_name = f'YTDLP_COOKIES_B64_{account_idx}'
            b64 = os.environ.get(env_var_name)
            if not b64:
                # No more numbered cookies
                break

            try:
                decoded = base64.b64decode(b64)
                is_valid = self._validate_cookies_content(decoded)
                target_path = f'/tmp/ytdlp_cookies_{account_idx}.txt'
                if is_valid:
                    with open(target_path, 'wb') as fd:
                        fd.write(decoded)
                    valid_cookies.append((account_idx, target_path, True))
                    self._logger.info('[cookies] Conta %d carregada e validada com sucesso (%d bytes).', account_idx, len(decoded))
                else:
                    self._logger.warning('[cookies] Conta %d rejeitada: conteúdo em %s não é um cookies.txt válido.', account_idx, env_var_name)
            except Exception as exc:
                self._logger.warning('[cookies] Erro ao processar %s (conta %d): %s', env_var_name, account_idx, exc)

            account_idx += 1
            if account_idx > 100:  # Safety limit
                break

        self._valid_cookies_list = valid_cookies
        self._cookies_loaded = True
        self._logger.info('[cookies] Total de contas carregadas com sucesso: %d', len(valid_cookies))
        return valid_cookies

    def _select_next_cookie(self) -> Optional[str]:
        """Seleciona o próximo cookie válido usando round-robin.
        
        Retorna o caminho do arquivo cookies.txt ou None se nenhum disponível.
        """
        valid_cookies = self._load_all_cookies()
        if not valid_cookies:
            return None

        # Round-robin selection
        selected = valid_cookies[self._cookie_round_robin_index % len(valid_cookies)]
        self._cookie_round_robin_index += 1

        account_num, cookie_path, is_valid = selected
        if is_valid and os.path.exists(cookie_path):
            self._logger.info('[cookies] Selecionada conta %d para extração.', account_num)
            return cookie_path
        return None

    def _ensure_cookiefile(self) -> Optional[str]:
        """Método legado de compatibilidade. Use _select_next_cookie() para nova lógica."""
        # Reset single-cookie tracking
        self._cookiefile_path = None
        self._cookiefile_valid = False

        # Check for explicit path (alta prioridade)
        cookies_path = os.environ.get('YTDLP_COOKIES_PATH')
        if cookies_path and os.path.exists(cookies_path):
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

        # For new multi-account logic, use _select_next_cookie()
        return None

    def _build_options(self, extra: Optional[Dict] = None, use_next_cookie: bool = False) -> Dict:
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

        # Use multi-account cookies if available; fallback to legacy single cookie
        if use_next_cookie:
            cookiefile = self._select_next_cookie()
            if cookiefile:
                opts['cookiefile'] = cookiefile
        else:
            # Legacy path remains available but not preferred
            cookiefile = self._ensure_cookiefile()
            if cookiefile and self._cookiefile_valid:
                opts['cookiefile'] = cookiefile

        # Fallback: cookies_from_browser
        if 'cookiefile' not in opts:
            cookies_browser = os.environ.get('YTDLP_COOKIES_FROM_BROWSER')
            if cookies_browser:
                opts['cookies_from_browser'] = cookies_browser

        proxy = os.environ.get('YTDLP_PROXY')
        if proxy:
            opts['proxy'] = proxy

        # Support for external PO Token provider (if configured)
        pot_provider_url = os.environ.get('YTDLP_POT_PROVIDER_URL')
        if pot_provider_url:
            # Use bgutil-ytdlp-pot-provider via extractor_args
            # Assuming plugin can reach external HTTP endpoint
            pot_args = {
                'youtube': {
                    'player_client': 'ios',  # iOS client often works with POT
                    'pot_provider': pot_provider_url,  # External provider URL
                }
            }
            if extra and 'extractor_args' in extra:
                # Merge with existing extractor_args
                extra_pot_args = extra.get('extractor_args', {})
                extra_pot_args.setdefault('youtube', {}).update(pot_args['youtube'])
                extra['extractor_args'] = extra_pot_args
            else:
                if not extra:
                    extra = {}
                extra['extractor_args'] = pot_args

        if extra:
            # Preserve extractor_args if passed explicitly
            extractor_args = extra.pop('extractor_args', None)
            if extractor_args:
                opts['extractor_args'] = extractor_args
            opts.update(extra)

        return opts

    def _run_ydl(self, url: str, extra: Optional[Dict] = None, use_next_cookie: bool = False) -> Dict:
        ydl_opts = self._build_options(extra, use_next_cookie=use_next_cookie)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    def extract_video_info(self, url: str) -> Dict:
        """
        Extrai informações de vídeo: título, duração, formatos disponíveis.
        
        Estratégia:
        - Tenta múltiplas estratégias de cliente (None, android, ios, web_creator)
        - Se bot-check, tenta próxima conta de cookies antes de desistir
        - Rotaciona entre contas disponíveis (round-robin)

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

        # Diagnostic logs about cookies and accounts
        valid_cookies = self._load_all_cookies()
        num_accounts = len(valid_cookies)
        self._logger.info('[cookies] Contas carregadas: %d', num_accounts)

        client_strategies = [None, 'android', 'ios', 'web_creator']
        errors = []
        info = None

        # Try client strategies + account rotation on bot-check
        for attempt_cookie_index in range(max(1, num_accounts)):
            for client in client_strategies:
                extra = {}
                if client:
                    extra['extractor_args'] = {'youtube': {'player_client': [client]}}
                try:
                    info = self._run_ydl(url, extra, use_next_cookie=(attempt_cookie_index > 0 or num_accounts > 0))
                    break
                except Exception as exc:
                    error_text = str(exc).lower()
                    bot_signals = ['sign in to confirm', 'cookies', 'botguard', 'po token', 'verify you are human']
                    is_bot_check = any(s in error_text for s in bot_signals)
                    
                    errors.append((client or 'default', error_text, is_bot_check))
                    
                    # Se for bot-check e temos mais contas, tenta proxima
                    if is_bot_check and attempt_cookie_index < num_accounts - 1:
                        self._logger.warning('[cookies] Bot-check detectado com cliente %s; tentando próxima conta.', client or 'default')
                        break  # Sai do loop de clientes, tenta nova conta
                    continue

            if info:
                break  # Sucesso! Sai de tudo

        if not info:
            # Analisar último erro para resposta
            if errors:
                last_client, last_error, last_is_bot = errors[-1]
                error_text = last_error
            else:
                error_text = 'Falha desconhecida ao extrair o vídeo.'
                last_is_bot = False

            readable_error = error_text.lower()
            bot_signals = ['sign in to confirm', 'cookies', 'botguard', 'po token', 'verify you are human']
            is_bot_error = any(s in readable_error for s in bot_signals)

            if is_bot_error:
                if num_accounts > 0:
                    # Tínhamos contas mas nenhuma funcionou
                    self._logger.warning('[cookies] Bot-check persistente mesmo depois de tentar %d conta(s): %s', num_accounts, error_text)
                    return {'error': 'Os cookies do YouTube parecem inválidos ou expiraram. Atualize as variáveis de ambiente ou tente novamente em alguns minutos.'}
                else:
                    # Sem contas configuradas
                    self._logger.warning('[cookies] Bot-check sem cookies configurados: %s', error_text)
                    return {'error': 'Este vídeo está temporariamente indisponível para download automático. Tente novamente em alguns minutos ou use outro vídeo.'}

            # Outros erros
            self._logger.info('[yt-dlp] extraction errors (total %d): %s', len(errors), errors)
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
