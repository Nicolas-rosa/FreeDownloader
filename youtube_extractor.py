"""
YouTube Stream Extractor & Format Selector

Módulo responsável por:
- Extrair informações de vídeos (título, duração, formatos disponíveis)
- Resolver URLs diretas para streams de áudio/vídeo
- Ler manifestos de mídia adaptativa (DASH)
- Selecionar formatos e qualidades baseado em critérios
- Retornar URL de stream ou lista de opções
"""

import yt_dlp
import json
from typing import Dict, List, Optional, Tuple


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

    def extract_video_info(self, url: str) -> Optional[Dict]:
        """
        Extrai informações de vídeo: título, duração, formatos disponíveis.

        Args:
            url: URL do YouTube (youtube.com, youtu.be, etc)

        Returns:
            Dicionário com metadados ou None se houver erro
        """
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'id': info.get('id'),
                    'title': info.get('title', 'Vídeo'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Desconhecido'),
                    'formats': self._extract_formats(info),
                }
        except Exception as e:
            return None

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
            ydl_opts = {**self.ydl_opts, 'format': format_id}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'url' in info:
                    return info['url']
                # Tentar recuperar de formatos
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
