# PO Token provider na VPS

O app usa o plugin Python `bgutil-ytdlp-pot-provider` para falar com o servidor
HTTP `bgutil-ytdlp-pot-provider`. O plugin e `yt-dlp >= 2025.05.22` precisam
estar instalados no ambiente que executa o FreeDownloader (`pip install -r
requirements.txt`).

## Subir o provider

Na VPS, mantenha a porta do provider apenas no loopback. O container oficial
escuta na porta 4416:

```bash
docker run --name bgutil-provider --detach --restart unless-stopped --init \
  --publish 127.0.0.1:4416:4416 \
  brainicism/bgutil-ytdlp-pot-provider
```

Confirme localmente, na própria VPS:

```bash
curl --fail http://127.0.0.1:4416/ping
```

## Nginx com TLS

Publique somente o nginx. Substitua os caminhos de certificado e o nome do
host pelos valores reais da sua infraestrutura; não coloque credenciais em
arquivos versionados.

```nginx
server {
    listen 80;
    server_name SEU_HOST;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name SEU_HOST;

    ssl_certificate     /etc/letsencrypt/live/SEU_HOST/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/SEU_HOST/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        # O arquivo deve ser usado como template pelo container nginx oficial;
        # ele substitui ${POT_PROVIDER_SECRET} na inicialização.
        if ($http_x_po_token_auth != "${POT_PROVIDER_SECRET}") {
            return 401;
        }

        proxy_pass http://127.0.0.1:4416;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 10s;
        proxy_read_timeout 60s;
    }
}
```

Salve-o como `default.conf.template`, não como configuração final. O container
oficial do nginx aplica `envsubst` aos arquivos em `/etc/nginx/templates`.
Defina o segredo na sessão, sem colocá-lo no arquivo, e inicie o proxy:

```bash
read -rsp 'POT provider secret: ' POT_PROVIDER_SECRET; export POT_PROVIDER_SECRET; echo
docker run --name pot-nginx --detach --restart unless-stopped \
  --network host \
  --env POT_PROVIDER_SECRET \
  --volume "$PWD/default.conf.template:/etc/nginx/templates/default.conf.template:ro" \
  nginx:alpine
```

O plugin upstream aceita somente `base_url`. O FreeDownloader instala um
adaptador pequeno e restrito ao provider que inclui
`X-PO-Token-Auth: <YTDLP_POT_PROVIDER_SECRET>` somente nas chamadas `/ping` e
`/get_pot`; o segredo não é enviado ao YouTube ou a URLs de mídia e nunca é
registrado em logs. Sem o pacote-plugin instalado, o app registra o problema e
segue para cookies/client spoof.

## Firewall

Não publique 4416. Libere somente HTTP/HTTPS para o nginx (e mantenha o acesso
administrativo SSH conforme a política da VPS):

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

## Configurar o FreeDownloader

Defina apenas uma URL base sem caminho, query, usuário ou senha:

```bash
export YTDLP_POT_PROVIDER_URL='https://SEU_HOST'
read -rsp 'POT provider secret: ' YTDLP_POT_PROVIDER_SECRET; export YTDLP_POT_PROVIDER_SECRET; echo
```

`YTDLP_POT_PROVIDER_SECRET` é opcional. Se estiver vazia, o nginx acima deve
remover o bloco de autenticação por header. Sem `YTDLP_POT_PROVIDER_URL`, o
comportamento existente permanece: cookies configurados e, por fim, os clients
alternativos do yt-dlp.

## Verificação

Depois de configurar, os logs do app devem indicar `Tentativa com estratégia:
pot`. O plugin correto usa o argumento:

```text
youtubepot-bgutilhttp:base_url=<URL_DO_PROVIDER>
```

O antigo `youtube:getpot_bgutil_baseurl` está depreciado. Para validar sem
nenhuma variável de ambiente:

```bash
env -u YTDLP_POT_PROVIDER_URL -u YTDLP_POT_PROVIDER_SECRET \
  python3 -m py_compile youtube_extractor.py
env -u YTDLP_POT_PROVIDER_URL -u YTDLP_POT_PROVIDER_SECRET \
  python3 -c 'from youtube_extractor import YouTubeStreamExtractor; print(YouTubeStreamExtractor()._pot_available)'
```

Fontes: [README oficial do provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider)
e [guia de PO Tokens do yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide).
