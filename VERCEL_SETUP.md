# Guia Rápido: Configurar FreeDownloader no Vercel

## 1️⃣ Deploy Inicial (se ainda não fez)

```bash
npm install -g vercel
cd /caminho/para/freedownloader
vercel
```

Siga as instruções interativas do Vercel CLI.

## 2️⃣ Variáveis de Ambiente (Vercel Dashboard)

Acesse: **Vercel → Seu Projeto → Settings → Environment Variables**

### Obrigatórias:
- **`SECRET_KEY`**: Chave secreta longa e aleatória (ex: `$(python3 -c 'import secrets; print(secrets.token_hex(32))')`)
- **`SUPPORT_EMAIL`**: Email de contato do site (ex: `seu-email@dominio.com`)

### Para Suporte a YouTube (Rotação de Cookies):

**Opção A: Uma única conta (compatível com versão anterior)**
```
YTDLP_COOKIES_B64 = [cole aqui o resultado de: base64 -w0 seu-cookies.txt]
```

**Opção B: Múltiplas contas (RECOMENDADO - mais robusto)**
```
YTDLP_COOKIES_B64_1 = [cookies da conta 1 em base64]
YTDLP_COOKIES_B64_2 = [cookies da conta 2 em base64]
YTDLP_COOKIES_B64_3 = [cookies da conta 3 em base64]
```

### Gerar Base64 de um Cookies.txt:

Na sua máquina local (onde o `cookies.txt` está):
```bash
base64 -w0 cookies.txt | xclip -selection clipboard
# No Mac: base64 -i cookies.txt | pbcopy
```

Depois, cole no Vercel (cada env var recebe um valor de arquivo cookies.txt diferente).

### Opcional: Proxy e PO Token

- **`YTDLP_PROXY`**: Proxy residencial, formato `http://user:pass@host:porta`
- **`YTDLP_POT_PROVIDER_URL`**: URL do servidor externo de PO Token (ex: `https://seu-pot-provider.dominio.com`)

## 3️⃣ Deploy

```bash
vercel --prod
```

Ou via GitHub: configure no Vercel Dashboard para fazer auto-deploy a cada push para `main`.

## 4️⃣ Teste Rápido

1. Acesse: **https://seu-projeto.vercel.app**
2. Aba "YouTube"
3. Cole uma URL do YouTube
4. Clique em "Analisar"
5. Se funcionar: show! ✅
6. Se der erro: vá em **Vercel → Logs** → procure `POST /extract-youtube` → analise a mensagem

## 5️⃣ Troubleshooting

### "Este vídeo está temporariamente indisponível"
- São 2 causas principais:
  1. Sem cookies configurados → configure `YTDLP_COOKIES_B64_1` (ou `_2`, `_3`...)
  2. Cookies expiraram → atualize com novos cookies do navegador

### "Os cookies parecem inválidos ou expiraram"
- Cookies estão configurados, mas:
  - Não são formato válido (verifique: deve começar com `# Netscape HTTP Cookie File`)
  - Estão expirados (gere novos via extensão de navegador)
  - Conta foi sinalizada pelo YouTube

### "Logs no Vercel mostram [cookies]"
- Procure por: `[cookies] Contas carregadas: X` — diz quantas contas estão OK
- Procure por: `[cookies] Selecionada conta Y` — diz qual conta foi usada
- Se diz `0 contas`, nenhum cookie configurado ou todos inválidos

## 6️⃣ Atualizar Cookies

Quando precisar renovar um cookie (expirou):

1. Na extensão do navegador, exporte novo `cookies.txt`
2. Na sua máquina: `base64 -w0 novo-cookies.txt | xclip -selection clipboard`
3. Vercel → Settings → Environment Variables
4. Edit `YTDLP_COOKIES_B64_1` (ou qual for)
5. Cole o novo valor
6. Save
7. Redeploy: **Deployments → (último deploy) → ... → Redeploy**

## 🎯 Checklist Final

- [ ] Projeto criado no Vercel
- [ ] `SECRET_KEY` e `SUPPORT_EMAIL` configurados
- [ ] `YTDLP_COOKIES_B64_1` (ou múltiplas) configurado(s)
- [ ] Deploy feito (`vercel --prod`)
- [ ] Testou com URL do YouTube → funciona ✅

---

**Precisa criar contas Google adicionais?**
1. Crie algumas contas (preferencialmente com dados diferentes)
2. Logue em cada uma no navegador
3. Use extensão para exportar `cookies.txt`
4. Gere base64 e configure no Vercel

Boa sorte! 🚀
