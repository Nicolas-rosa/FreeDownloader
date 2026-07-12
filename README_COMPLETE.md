# FreeDownloader — Download seguro de MP3/MP4

Site moderno e responsivo para download de arquivos MP3 e MP4 de fontes que você possui direitos autorais. Suporte nativo para YouTube com extração de streams e seleção de qualidade.

## ✨ Características Principais

- **URL Direta**: Aceita URLs diretas para arquivos MP3/MP4 hospedados em qualquer servidor público
- **🎬 YouTube Support**: Suporte nativo para vídeos do YouTube usando yt-dlp
- **📊 Seleção de Qualidade**: Escolha entre formatos de áudio (MP3) e vídeo (MP4) em múltiplas resoluções
- **🔗 Stream Adaptativo**: Lê manifesto DASH, extrai informações e seleciona melhor formato
- **🔒 Segurança Robusta**: Validação de IPs privados, limite de 200MB, confirmação obrigatória de direitos
- **🎨 UI Premium**: Design responsivo com abas, seletor interativo, espaço para AdSense
- **⚖️ Conformidade Legal**: Termos, Privacidade, DMCA, avisos destacados

## 🚀 Setup Rápido

### Pré-requisitos
- Python 3.8+
- Conexão com internet

### Instalação

```bash
cd /home/castro_war/Documentos/Worktable/farmarmoney/freedownloader

# Criar ambiente virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependências
pip install -r requirements.txt
```

### Rodar o servidor

```bash
# Configurar variáveis (opcional)
export SECRET_KEY="sua-chave-secreta-super-longa"
export SUPPORT_EMAIL="seu-email@dominio.com"
export FLASK_DEBUG=1

# Iniciar
flask run
```

Acesse **http://localhost:5000**

## 📖 Como Usar

### Modo URL Direta
1. Clique na aba "URL Direta"
2. Cole a URL do arquivo (MP3 ou MP4)
3. Confirme que você possui os direitos
4. Clique em "Baixar"

### Modo YouTube
1. Clique na aba "YouTube"
2. Cole a URL do seu vídeo (`youtube.com/watch?v=...` ou `youtu.be/...`)
3. Clique em "Analisar ⚙"
4. Selecione formato (Áudio MP3 ou Vídeo MP4)
5. Escolha qualidade/resolução
6. Confirme que é seu vídeo ou tem autorização
7. Clique em "Baixar ↓"

## 🔧 Arquitetura Técnica

### Módulo: `youtube_extractor.py`

Responsável por extrair informações e resolver streams do YouTube:

```python
YouTubeStreamExtractor
├── extract_video_info(url: str) → Dict
│   └─ Retorna: id, título, duração, uploader, formatos
├── get_stream_url(url: str, format_id: str) → str
│   └─ Retorna URL de stream público
├── get_best_audio_stream(url: str) → Tuple[str, str]
│   └─ Retorna: (url_audio, filename.mp3)
└── get_best_video_stream(url: str) → Tuple[str, str]
    └─ Retorna: (url_video, filename.mp4)
```

**Funcionamento interno:**
1. `yt-dlp` extrai informações de vídeo
2. Analisa manifesto DASH (adaptive media)
3. Agrupa formatos por tipo (audio vs video)
4. Seleciona melhor qualidade em cada resolução
5. Retorna URL de stream público e metadados

### Endpoints Flask (`app.py`)

| Rota | Método | Descrição |
|------|--------|-----------|
| `/` | GET | Página principal com abas |
| `/download` | POST | Download de URL direta |
| `/extract-youtube` | POST | Extrai formatos → JSON |
| `/download-youtube` | POST | Download de stream do YouTube |
| `/terms` | GET | Termos de uso |
| `/privacy` | GET | Política de privacidade |
| `/dmca` | GET | Política DMCA |

### Fluxo de Extração YouTube

```
Usuário submete URL
           ↓
POST /extract-youtube
           ↓
yt-dlp.extract_info()
           ↓
_extract_formats() → Lista de opções
           ↓
Retorna JSON: {id, title, duration, formats: [...]}
           ↓
Frontend renderiza <select> com opções (áudio + vídeo)
           ↓
Usuário seleciona format_id
           ↓
POST /download-youtube {url, format_id, type}
           ↓
get_stream_url(format_id) → URL pública
           ↓
Valida e faz streaming → Cliente
```

### Frontend (`templates/index.html`)

- **Abas**: Alterna entre URL Direta e YouTube
- **Extrator Interativo**: JavaScript que chama `/extract-youtube`
- **Loading**: Spinner enquanto analisa vídeo
- **Seletor de Qualidade**: `<select>` preenchido dinamicamente
- **Agrupamento**: Opções de áudio (MP3) e vídeo (MP4) separadas

### Estilos (`static/css/style.css`)

- Design responsivo (mobile-first)
- 4 passos adicionados (Cole → Selecione → Confirme → Salve)
- Abas com indicador visual
- Componentes de loading e extração
- Gradientes e cores consistentes (aqua/navy/paper)

## 🛡️ Camadas de Segurança

### 1. Validação de URL
- Apenas HTTPS/HTTP
- Rejeita URLs ambíguas

### 2. Bloqueio de IPs Privados
- Não acessa `127.0.0.1` ou `localhost`
- Rejeita `192.168.x.x`, `10.0.0.x` (intranets)
- Rejeita `169.254.x.x` (link-local)
- Impede acesso a serviços internos

### 3. Limite de Tamanho
- Máximo 200 MB por arquivo
- Interrompe download se exceder

### 4. Confirmação Obrigatória
- Checkbox explícito: "Confirmo que sou titular dos direitos..."
- Armazenado em logs (opcional)

### 5. Timeouts e Sanitização
- 10s para verificação (HEAD)
- 30s para download (GET)
- Nomes de arquivo sanitizados (sem `../`, `/etc/`, etc)

## 📄 Conformidade Legal

### Páginas Incluídas

1. **Termos de Uso** — Proíbe infração, DRM evasion, burla de TOS
2. **Privacidade** — Explica coleta mínima de dados
3. **DMCA** — Instruções para reportar conteúdo

### Conformidade Google AdSense

✅ **Aprovável se:**
- Conteúdo original (blog, guias adicionados)
- UI clara e profissional
- Avisos destacados sobre direitos
- Páginas legais completas
- Sem conteúdo indevido

❌ **Rejeitável se:**
- Monetizar conteúdo pirateado
- Faltar Termos/Privacidade
- UI pobre ou "thin content"

**Para adicionar AdSense:**

1. Obter código do Google AdSense
2. Editar [templates/base.html](templates/base.html)
3. Inserir no `<div class="ad-section">`

```html
<div class="ad-section container">
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-YOUR_ID"></script>
  <ins class="adsbygoogle" ... data-ad-slot="..."></ins>
</div>
```

4. Testar localmente
5. Submeter para revisor do Google

## 📦 Dependências

```
Flask>=2.2          # Web framework
requests>=2.28      # HTTP client
yt-dlp>=2024.1.1    # YouTube extractor & format selector
```

### Por que não youtube-dl?
- **yt-dlp** é fork mais ativo de youtube-dl
- Suporta novas proteções do YouTube
- Updates frequentes (semanal)
- Melhor performance na extração de manifesto

## 🎓 Termos Técnicos Usados

| Termo | Definição |
|-------|-----------|
| **Extractor** | Módulo que extrai metadados de vídeos |
| **Video Info** | Metadados extraídos (título, duração, formatos) |
| **Stream URL** | URL pública do stream de áudio/vídeo |
| **Signature** | Parâmetro ofuscado do YouTube (resolvido por yt-dlp) |
| **Manifest** | Arquivo XML/JSON descrevendo formatos disponíveis |
| **DASH** | Dynamic Adaptive Streaming over HTTP (vídeo + áudio separados) |
| **Format Selector** | Lógica que escolhe melhor formato para qualidade |
| **Converter URL** | Transformar links de vídeo em URLs diretas de stream |
| **Adaptive Media** | Streams que se ajustam à conexão do usuário |

## 🧪 Testes Manuais

```bash
# Testar URL direta (MP3 público)
http://localhost:5000
→ Cole: https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3

# Testar YouTube (seu próprio vídeo)
http://localhost:5000
→ Aba: YouTube
→ Cole: https://www.youtube.com/watch?v=SEU_VIDEO_ID
→ Clique: Analisar ⚙
→ Selecione: Qualidade
→ Confirme e baixe
```

## 🌍 Deployment (Produção)

### Ambiente

```bash
export SECRET_KEY="gere-com-secrets.token_urlsafe(32)"
export SUPPORT_EMAIL="seu-email@seu-dominio.com"
export FLASK_DEBUG=0
```

### Servidor WSGI (Gunicorn)

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

### Reverse Proxy (Nginx)

```nginx
server {
    listen 80;
    server_name seu-dominio.com;
    location / {
        proxy_pass http://localhost:8000;
    }
}
```

## 📞 Suporte

- **Termos**: Veja [Termos de Uso](templates/terms.html)
- **Privacidade**: Veja [Política de Privacidade](templates/privacy.html)
- **DMCA**: Veja [Política DMCA](templates/dmca.html)

---

**FreeDownloader** — Download seguro de seus arquivos. Sem DRM evasion, sem piraria. Apenas seus direitos.

Último update: **2026-07-11**  
Versão: **1.1.0 (com YouTube support)**
