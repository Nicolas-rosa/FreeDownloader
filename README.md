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

Depuração e configuração de YouTube:

### Suporte a Cookies Autenticados (Rotação de Múltiplas Contas)

Para vídeos que exigem login no YouTube, o app suporta rotação entre múltiplas contas de cookies:

**Formato legacy (compatível - uma única conta):**
- `YTDLP_COOKIES_B64`: Um único arquivo cookies.txt em base64 (tratado como conta 1)

**Novo formato (múltiplas contas - recomendado para robustez):**
- `YTDLP_COOKIES_B64_1`: Primeira conta
- `YTDLP_COOKIES_B64_2`: Segunda conta
- `YTDLP_COOKIES_B64_3`: Terceira conta
- ... e assim por diante (`_4`, `_5`, `_N`)

**Como gerar cada variável:**

1. Exporte um `cookies.txt` de uma conta Google logada (use extensão de navegador como "Get cookies.txt"):
   ```bash
   base64 -w0 cookies.txt > cookies_b64.txt
   ```
2. Copie o conteúdo de `cookies_b64.txt` na íntegra (Ctrl+A, Ctrl+C)
3. No painel Vercel → Settings → Environment Variables:
   - Crie uma nova variável (exemplo: `YTDLP_COOKIES_B64_1`)
   - Cole o valor full do arquivo base64
   - Salve

**Como funciona a rotação:**
- O app tenta extrair vídeos com a primeira conta disponível
- Se encontrar erro de bot-check, tenta automaticamente a próxima conta  (sem ação do usuário)
- Usa round-robin entre contas válidas para distribuir a carga
- Não suba arquivos de cookies para o Git; são secrets do Vercel

### PO Token Provider (Funcionalidade Avançada)

Para máxima robustez contra o bot-check do YouTube (hoje o método mais confiável), pode-se usar um serviço externo de PO Token:

- Requer: Um servidor separado rodando `bgutil-ytdlp-pot-provider` (ou equivalente) com URL HTTP pública
- Configuração:
  1. Configure uma VPS e rode o serviço POT (fora do escopo do FreeDownloader)
  2. No Vercel, crie a env var: `YTDLP_POT_PROVIDER_URL=https://seu-pot-provider.dominio.com`
  3. O app usará esse provider automaticamente se configurado
- **Nota:** Isso é opcional. O app funciona normalmente com cookies sem esse provider.

### Outras Variáveis de Ambiente

- `YTDLP_PROXY`: Proxy residencial, formato `http://usuario:senha@host:porta` (opcional)
- `YTDLP_COOKIES_PATH`: Caminho direto a um arquivo `cookies.txt` na máquina (localhost apenas)
- `YTDLP_COOKIES_FROM_BROWSER`: Fallback para extrair cookies do navegador local (ex: `firefox` ou `chrome`)

### Validação de Cookies

- Todos os cookies são validados antes de usar (formato Netscape, presença de youtube.com)
- Se um cookie for inválido ou expirado, o app o rejeita graciosamente e tenta a próxima conta
- Erros são logados sem expor o conteúdo do cookie (apenas metadados: tamanho, validade)

Observações legais:
- Este projeto não auxilia em burlar proteções ou TOS de terceiros. Use apenas arquivos que você possui direitos.
