# APK Android — FreeDownloader

Este diretório contém o aplicativo Android nativo que abre o FreeDownloader publicado e delega os downloads ao gerenciador de downloads do Android.

## Antes de gerar o APK

1. Publique o backend Flask em HTTPS (por exemplo, no Vercel).
2. Na primeira abertura do app, informe a URL HTTPS publicada. Ela é salva somente no dispositivo. Para trocar depois, use o menu **Alterar servidor**.

Alternativamente, defina a URL definitiva em `app/src/main/res/values/strings.xml`, no valor `default_server_url`, antes da compilação.

## Gerar APK de teste

Com Android SDK (API 35) e JDK 17 instalados:

```bash
cd android
gradle assembleDebug
```

O arquivo será criado em `app/build/outputs/apk/debug/app-debug.apk`.

## Gerar APK para distribuição

Crie uma chave e configure a assinatura de release no Gradle antes de executar:

```bash
gradle assembleRelease
```

Para publicar na Play Store, prefira gerar um Android App Bundle (`bundleRelease`) e siga os requisitos de assinatura e de política da loja.
