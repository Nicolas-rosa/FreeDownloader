"""Extração de metadados e streams do YouTube com fallback de autenticação.

Baseado nos patterns do MeTube (alexta69/metube):
  - YTDL_OPTIONS como JSON env var (merge 3 camadas: global → preset → override)
  - cookiefile como opção yt-dlp (sem rotação manual)
  - _build_ydl_options() separado do estado global
"""

import base64
import json
import logging
import os
import time
from copy import deepcopy
from typing import Any, Dict, Iterator, List, Literal, Optional, Tuple
from urllib.parse import urlsplit

import yt_dlp


AuthStrategy = Literal['pot', 'cookies', 'client_spoof']
_CACHE_TTL_SECONDS = 900
_VIDEO_INFO_CACHE: Dict[str, Dict] = {}
_BOT_SIGNALS = ('sign in to confirm', 'cookies', 'botguard', 'po token', 'verify you are human')
_SPOOF_CLIENTS = (None, 'android', 'ios', 'web_creator')


def _load_json_env(key: str, default: Any = None) -> Any:
    """Load a JSON-serialized env var with error handling (MeTube pattern)."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        logging.getLogger(__name__).warning('[config] %s ignored: invalid JSON (%s)', key, exc)
        return default


def _load_cookiefile_from_b64(env_var: str, output_path: str) -> Optional[str]:
    """Decode a base64-encoded Netscape cookie file and write to disk.
    
    Returns the file path if successful, None otherwise.
    """
    cookie_b64 = os.environ.get(env_var)
    if not cookie_b64:
        return None
    try:
        content = base64.b64decode(cookie_b64, validate=True)
        if not content:
            return None
        # Validação básica: deve ter ao menos uma linha com 7 tabs (Netscape format)
        text = content.decode('utf-8', errors='replace')
        lines = [line for line in text.splitlines() if line and not line.startswith('#')]
        has_valid_row = any(len(line.split('\t')) >= 7 for line in lines)
        if not has_valid_row:
            logging.getLogger(__name__).warning('[cookies] %s ignorado: formato Netscape inválido.', env_var)
            return None
        # Usar replace atômico para evitar escrita parcial
        tmp_path = f"{output_path}.tmp"
        with open(tmp_path, 'wb') as f:
            f.write(content)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, output_path)
        logging.getLogger(__name__).info('[cookies] %s decodificado (%d bytes).', env_var, len(content))
        return output_path
    except (ValueError, OSError) as exc:
        logging.getLogger(__name__).warning('[cookies] %s ignorado: %s', env_var, exc)
        return None


class YouTubeStreamExtractor:
    """Extrai informações e streams, sem depender de cookies quando há POT.

    Estrutura de configuração (inspirada no MeTube):
      1. YTDL_OPTIONS global (env var JSON) → defaults hardcoded
      2. YTDL_OPTIONS_PRESETS (dict nomeado opcional)
      3. Overrides por chamada (via _build_ydl_options)
    """

    def __init__(self):
        self._logger = logging.getLogger(__name__)
        if not logging.getLogger().handlers:
            logging.basicConfig(level=logging.INFO)

        # ── Camada 1: defaults hardcoded (base segura) ──────────────────
        self._default_opts: Dict[str, Any] = {
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

        # ── Camada 1b: YTDL_OPTIONS global (JSON env var, merge sobre defaults) ──
        self._global_opts: Dict[str, Any] = deepcopy(self._default_opts)
        env_opts = _load_json_env('YTDL_OPTIONS', {})
        if isinstance(env_opts, dict):
            self._global_opts.update(env_opts)
            if env_opts:
                self._logger.info('[config] YTDL_OPTIONS global carregada com %d chaves.', len(env_opts))
        else:
            self._logger.warning('[config] YTDL_OPTIONS deve ser um objeto JSON; ignorado.')

        # ── Camada 2: YTDL_OPTIONS_PRESETS (presets nomeados) ──
        self._presets: Dict[str, Dict[str, Any]] = {}
        env_presets = _load_json_env('YTDL_OPTIONS_PRESETS', {})
        if isinstance(env_presets, dict):
            self._presets = env_presets
            if env_presets:
                self._logger.info('[config] %d preset(s) carregado(s): %s', len(env_presets), sorted(env_presets.keys()))
        else:
            self._logger.warning('[config] YTDL_OPTIONS_PRESETS deve ser um objeto JSON; ignorado.')

        # ── ALLOW_YTDL_OPTIONS_OVERRIDES (flag de segurança) ──
        self._allow_overrides = os.environ.get('ALLOW_YTDL_OPTIONS_OVERRIDES', '').lower() in ('true', '1', 'yes')

        # ── Cookie file (cookiefile como opção yt-dlp, sem rotação manual) ──
        self._cookiefile = self._resolve_cookiefile()
        if self._cookiefile and os.path.exists(self._cookiefile):
            self._global_opts['cookiefile'] = self._cookiefile
            self._logger.info('[cookies] Arquivo de cookies encontrado em %s.', self._cookiefile)
        else:
            self._logger.debug('[cookies] Nenhum arquivo de cookies disponível.')

        # ── POT (Proof of Origin) ──
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

    # ── Config helpers ──────────────────────────────────────────────────

    def _resolve_cookiefile(self) -> Optional[str]:
        """Resolve cookiefile: YTDL_OPTIONS > YTDLP_COOKIES_B64 > YTDLP_COOKIES_PATH.

        MeTube pattern: cookiefile é uma opção do yt-dlp, não lógica separada.
        """
        # 1. YTDL_OPTIONS já pode conter 'cookiefile'
        if 'cookiefile' in self._global_opts:
            path = self._global_opts['cookiefile']
            if isinstance(path, str) and os.path.exists(path):
                return path

        # 2. YTDLP_COOKIES_B64 (decodifica e salva em /tmp)
        cookie_path = _load_cookiefile_from_b64('YTDLP_COOKIES_B64', '/tmp/ytdlp_cookies.txt')
        if cookie_path:
            return cookie_path

        # 3. YTDLP_COOKIES_PATH (caminho direto para arquivo Netscape)
        path_from_env = os.environ.get('YTDLP_COOKIES_PATH')
        if path_from_env and os.path.isfile(path_from_env):
            return path_from_env

        # 4. cookies_from_browser (fallback para desktop)
        browser = os.environ.get('YTDLP_COOKIES_FROM_BROWSER')
        if browser:
            self._global_opts['cookies_from_browser'] = browser
            self._logger.info('[cookies] Usando cookies_from_browser=%s', browser)

        return None

    def _load_pot_plugin(self):
        try:
            from yt_dlp_plugins.extractor.getpot_bgutil_http import BgUtilHTTPPTP
            return BgUtilHTTPPTP
        except ImportError:
            return None

    def _pot_provider_label(self) -> str:
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
        """Inclui o segredo apenas nas chamadas HTTP do provider bgutil."""
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

    # ── Merge pattern (MeTube: global → presets → overrides) ────────────

    def _build_ydl_options(
        self,
        extra: Optional[Dict[str, Any]] = None,
        strategy: AuthStrategy = 'client_spoof',
        ytdl_options_presets: Optional[List[str]] = None,
        ytdl_options_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Constrói opções com merge em 3 camadas (MeTube pattern).

        Ordem de precedência (último vence):
          1. self._global_opts (YTDL_OPTIONS env var + defaults)
          2. Presets nomeados (YTDL_OPTIONS_PRESETS)
          3. Overrides por chamada (ytdl_options_overrides)
          4. Estratégia de autenticação (POT extractor_args)

        Args:
            extra: Opções adicionais avulsas.
            strategy: Estratégia de autenticação.
            ytdl_options_presets: Lista de nomes de presets para aplicar.
            ytdl_options_overrides: Dict de opções para sobrescrever.

        Returns:
            Dict com as opções mescladas.
        """
        opts = deepcopy(self._global_opts)

        # Aplica presets nomeados (Camada 2)
        for preset_name in ytdl_options_presets or []:
            preset = self._presets.get(preset_name)
            if preset is not None:
                if isinstance(preset, dict):
                    opts.update(preset)
                    self._logger.debug('[preset] Aplicado preset "%s": %d chave(s).', preset_name, len(preset))
                else:
                    self._logger.warning('[preset] Preset "%s" ignorado: não é um dict.', preset_name)
            else:
                self._logger.warning('[preset] Preset "%s" não encontrado.', preset_name)

        # Aplica overrides por chamada (Camada 3)
        if ytdl_options_overrides and isinstance(ytdl_options_overrides, dict):
            if self._allow_overrides:
                opts.update(ytdl_options_overrides)
                self._logger.debug('[override] Aplicados %d override(s).', len(ytdl_options_overrides))
            else:
                self._logger.warning('[override] ALLOW_YTDL_OPTIONS_OVERRIDES=false; overrides ignorados.')

        # Aplica extra avulso
        if extra:
            opts.update(extra)

        # Aplica estratégia de autenticação
        if strategy == 'pot' and self._pot_available:
            extractor_args = opts.setdefault('extractor_args', {})
            pot_args = extractor_args.setdefault('youtubepot-bgutilhttp', {})
            pot_args['base_url'] = [self._pot_provider_url]

        return opts

    # ── Estratégia de fallback ──────────────────────────────────────────

    def _attempts(self) -> Iterator[Tuple[AuthStrategy, Optional[str], bool]]:
        """POT primeiro; cookies são apenas fallback; spoof sempre encerra a cadeia."""
        if self._pot_available:
            yield 'pot', None, False

        # Cookies: se tem cookiefile configurado (sem rotação)
        if self._cookiefile and os.path.exists(self._cookiefile):
            yield 'cookies', None, False
        elif os.environ.get('YTDLP_COOKIES_FROM_BROWSER'):
            yield 'cookies', None, False

        for client in _SPOOF_CLIENTS:
            yield 'client_spoof', client, False

    def _extract_with_fallback(
        self,
        url: str,
        extra: Optional[Dict] = None,
        ytdl_options_presets: Optional[List[str]] = None,
        ytdl_options_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        """Extrai info_dict com fallback entre estratégias de autenticação.

        Usa _build_ydl_options para merge de opções em cada tentativa.
        """
        errors = []
        for strategy, client, _ in self._attempts():
            attempt_extra = deepcopy(extra) if extra else {}
            if client:
                client_args = attempt_extra.setdefault('extractor_args', {})
                client_args.setdefault('youtube', {})['player_client'] = [client]

            self._logger.info('[auth] Tentativa: %s%s', strategy, f' ({client})' if client else '')

            try:
                options = self._build_ydl_options(
                    extra=attempt_extra,
                    strategy=strategy,
                    ytdl_options_presets=ytdl_options_presets,
                    ytdl_options_overrides=ytdl_options_overrides,
                )
                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.extract_info(url, download=False)
            except Exception as exc:
                message = str(exc).lower()
                errors.append(message)
                kind = 'bot-check' if any(signal in message for signal in _BOT_SIGNALS) else 'erro'
                self._logger.warning('[auth] %s falhou (%s); tentando fallback.', strategy, kind)

        raise RuntimeError(errors[-1] if errors else 'Falha ao extrair o vídeo.')

    # ── API pública ─────────────────────────────────────────────────────

    def extract_video_info(
        self,
        url: str,
        ytdl_options_presets: Optional[List[str]] = None,
        ytdl_options_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        """Extrai metadados do vídeo com cache e fallback de autenticação.

        Args:
            url: URL do YouTube.
            ytdl_options_presets: Lista de presets para aplicar (ex: ['high_quality']).
            ytdl_options_overrides: Opções para sobrescrever por chamada.

        Returns:
            Dict com id, title, duration, uploader, formats ou {'error': msg}.
        """
        cache_key = f"{url.strip()}:{json.dumps(ytdl_options_presets or [])}:{json.dumps(ytdl_options_overrides or {})}"
        cached = _VIDEO_INFO_CACHE.get(cache_key)
        if cached and cached['expires'] > time.time():
            return cached['value']

        try:
            info = self._extract_with_fallback(
                url,
                ytdl_options_presets=ytdl_options_presets,
                ytdl_options_overrides=ytdl_options_overrides,
            )
        except Exception as exc:
            self._logger.warning('[youtube] Extração falhou após todos os fallbacks: %s', str(exc)[:160])
            return {'error': 'Não foi possível acessar este vídeo agora. Tente novamente mais tarde.'}

        formats = self._extract_formats(info)
        result = {
            'id': info.get('id'),
            'title': info.get('title', 'Vídeo'),
            'duration': info.get('duration', 0),
            'uploader': info.get('uploader', 'Desconhecido'),
            'formats': formats,
        }
        _VIDEO_INFO_CACHE[cache_key] = {'expires': time.time() + _CACHE_TTL_SECONDS, 'value': result}
        return result

    @staticmethod
    def _extract_formats(info: Dict) -> List[Dict]:
        """Extrai formatos de áudio e vídeo do info_dict.

        Separado da extração principal (MeTube pattern: dl_formats.py).
        """
        formats = []

        # Melhor áudio disponível
        audio_formats = [
            item for item in info.get('formats', [])
            if item.get('vcodec') == 'none' and item.get('acodec') != 'none'
        ]
        if audio_formats:
            best_audio = max(audio_formats, key=lambda item: item.get('abr', 0) or 0)
            formats.append({
                'format_id': best_audio['format_id'],
                'ext': 'mp3',
                'type': 'audio',
                'quality': f"{best_audio.get('abr', 128)}kbps",
                'format_note': best_audio.get('format_note', 'Áudio'),
                'filesize': best_audio.get('filesize'),
            })

        # Melhor vídeo por resolução
        best_by_height: Dict[int, Dict] = {}
        for item in info.get('formats', []):
            if item.get('vcodec') == 'none' or item.get('acodec') != 'none':
                continue
            height = item.get('height') or 0
            if height and (height not in best_by_height or (item.get('vbr') or 0) > (best_by_height[height].get('vbr') or 0)):
                best_by_height[height] = item

        for height in sorted(best_by_height, reverse=True):
            item = best_by_height[height]
            formats.append({
                'format_id': item['format_id'],
                'ext': 'mp4',
                'type': 'video',
                'quality': f'{height}p',
                'format_note': item.get('format_note', f'{height}p'),
                'filesize': item.get('filesize'),
            })

        return formats

    @staticmethod
    def _safe_stream_headers(headers: Optional[Dict]) -> Dict[str, str]:
        """Remove headers sensíveis antes de expor ao client."""
        sensitive = {'cookie', 'authorization', 'x-po-token-auth'}
        return {
            str(key): str(value)
            for key, value in (headers or {}).items()
            if str(key).lower() not in sensitive
        }

    def get_stream(
        self,
        url: str,
        format_id: str,
        ytdl_options_presets: Optional[List[str]] = None,
        ytdl_options_overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, object]]:
        """Obtém URL direta do stream para um formato específico.

        Args:
            url: URL do YouTube.
            format_id: ID do formato (ex: 'bestaudio/best', '137+140').
            ytdl_options_presets: Presets para aplicar.
            ytdl_options_overrides: Overrides por chamada.

        Returns:
            Dict com 'url' e 'headers' ou None.
        """
        try:
            extra = {'format': format_id}
            info = self._extract_with_fallback(
                url,
                extra=extra,
                ytdl_options_presets=ytdl_options_presets,
                ytdl_options_overrides=ytdl_options_overrides,
            )
        except Exception as exc:
            self._logger.warning('[youtube] Stream indisponível: %s', str(exc)[:160])
            return None

        selected = next(
            (item for item in info.get('formats', []) if item.get('format_id') == format_id),
            info,
        )
        stream_url = selected.get('url') or info.get('url')
        if not stream_url:
            return None

        return {
            'url': stream_url,
            'headers': self._safe_stream_headers(
                selected.get('http_headers') or info.get('http_headers')
            ),
        }

    def get_stream_url(
        self,
        url: str,
        format_id: str,
        ytdl_options_presets: Optional[List[str]] = None,
        ytdl_options_overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Shorthand para obter apenas a URL do stream."""
        stream = self.get_stream(
            url, format_id,
            ytdl_options_presets=ytdl_options_presets,
            ytdl_options_overrides=ytdl_options_overrides,
        )
        return stream['url'] if stream else None

    def get_best_audio_stream(
        self,
        url: str,
        ytdl_options_presets: Optional[List[str]] = None,
        ytdl_options_overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[Tuple[str, str]]:
        """Obtém melhor stream de áudio + nome de arquivo."""
        stream = self.get_stream(
            url, 'bestaudio/best',
            ytdl_options_presets=ytdl_options_presets,
            ytdl_options_overrides=ytdl_options_overrides,
        )
        if not stream:
            return None
        info = self.extract_video_info(url)
        title = info.get('title', 'audio').replace('/', '_') if not info.get('error') else 'audio'
        return stream['url'], f'{title}.mp3'

    def get_best_video_stream(
        self,
        url: str,
        ytdl_options_presets: Optional[List[str]] = None,
        ytdl_options_overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[Tuple[str, str]]:
        """Obtém melhor stream de vídeo + nome de arquivo."""
        stream = self.get_stream(
            url, 'best[ext=mp4]/best',
            ytdl_options_presets=ytdl_options_presets,
            ytdl_options_overrides=ytdl_options_overrides,
        )
        if not stream:
            return None
        info = self.extract_video_info(url)
        title = info.get('title', 'video').replace('/', '_') if not info.get('error') else 'video'
        return stream['url'], f'{title}.mp4'


_extractor: Optional[YouTubeStreamExtractor] = None


def get_extractor() -> YouTubeStreamExtractor:
    """Singleton factory."""
    global _extractor
    if _extractor is None:
        _extractor = YouTubeStreamExtractor()
    return _extractor