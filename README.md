# FreeDownloader

Pequeno site para baixar arquivos MP3/MP4 a partir de uma URL direta — projetado para uso com arquivos que você possui os direitos.

Instalação rápida (Linux):

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=app.py
export SECRET_KEY="troque-por-uma-chave-longa-e-aleatoria"
export SUPPORT_EMAIL="contato@seu-dominio.com"
flask run
```

Notas importantes para aprovação no Google AdSense:
- Não permita conteúdo infrator. Inclua Termos, Política de Privacidade e DMCA (já incluso).
- Insira o script do AdSense apenas depois de revisar as políticas do Google e ter conteúdo original.
- Evite páginas “thin content”: adicione descrição, ajuda e conteúdo editorial para cada página.
- Antes de publicar, substitua o e-mail padrão de contato e preencha as informações reais do responsável pelo site.

Depuração de YouTube no deploy:
- Para vídeos que exigem login, use cookies autenticados do navegador.
- Exporte um `cookies.txt` da conta Google logada e configure em Vercel como `YTDLP_COOKIES_B64`.
- Converta o arquivo para Base64 antes de copiar para a variável de ambiente:
  ```bash
  base64 -w0 cookies.txt
  ```
- Não suba o arquivo de cookies para o Git; mantenha-o como variável de ambiente/secret no painel do Vercel.
- Se necessário, use proxy residencial com `YTDLP_PROXY` no Vercel, por exemplo `http://user:pass@host:port`.
- Se os cookies expirarem ou perderem validade, gere um novo `cookies.txt` e atualize `YTDLP_COOKIES_B64`.

Observações legais:
- Este projeto não auxilia em burlar proteções ou TOS de terceiros. Use apenas arquivos que você possui direitos.
