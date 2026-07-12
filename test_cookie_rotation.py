#!/usr/bin/env python3
"""
Script de teste para validar a lógica de rotação de cookies e PO Token provider.

Testa:
1. Sem env vars → app funciona (fallback)
2. Com YTDLP_COOKIES_B64 (formato antigo) → funciona como conta 1
3. Com YTDLP_COOKIES_B64_1 e _2 (inválidos) → rejeitados, logs apropriados
4. Com YTDLP_POT_PROVIDER_URL → opcão carregada sem erros
"""

import os
import sys
import base64
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(name)s] %(message)s')

# Import after path setup
sys.path.insert(0, os.path.dirname(__file__))
from youtube_extractor import YouTubeStreamExtractor

def test_no_cookies():
    """Teste 1: Sem cookies configurados."""
    print("\n=== TESTE 1: Sem cookies configurados ===")
    # Limpar env vars
    for key in list(os.environ.keys()):
        if 'YTDLP_COOKIES' in key:
            del os.environ[key]
    
    extrator = YouTubeStreamExtractor()
    cookies = extrator._load_all_cookies()
    print(f"Contas carregadas: {len(cookies)}")
    assert len(cookies) == 0, "Deveria ter 0 contas"
    print("✓ PASSOU: App funciona sem cookies (fallback)")


def test_legacy_single_cookie():
    """Teste 2: Formato antigo (YTDLP_COOKIES_B64 sem número)."""
    print("\n=== TESTE 2: Formato legado (YTDLP_COOKIES_B64) ===")
    # Limpar env vars
    for key in list(os.environ.keys()):
        if 'YTDLP_COOKIES' in key:
            del os.environ[key]
    
    # Simular um cookie inválido (qualquer string base64 que não é cookies.txt válido)
    fake_cookie = base64.b64encode(b"# This is not a real cookie file").decode()
    os.environ['YTDLP_COOKIES_B64'] = fake_cookie
    
    extrator = YouTubeStreamExtractor()
    cookies = extrator._load_all_cookies()
    print(f"Contas carregadas: {len(cookies)}")
    print(f"Detalhes: {cookies}")
    # Deveria tentar carregar como conta 1 mas rejeitar por formato inválido
    assert len(cookies) == 0, "Deveria rejeitar cookie inválido"
    print("✓ PASSOU: Formato legado processado, cookie inválido rejeitado")


def test_multiple_invalid_cookies():
    """Teste 3: Múltiplas contas  (inválidas para teste de lógica)."""
    print("\n=== TESTE 3: Múltiplas contas (inválidas) ===")
    # Limpar env vars
    for key in list(os.environ.keys()):
        if 'YTDLP_COOKIES' in key:
            del os.environ[key]
    
    # Configurar dois cookies inválidos
    fake1 = base64.b64encode(b"# Invalid cookie 1").decode()
    fake2 = base64.b64encode(b"# Invalid cookie 2").decode()
    os.environ['YTDLP_COOKIES_B64_1'] = fake1
    os.environ['YTDLP_COOKIES_B64_2'] = fake2
    
    extrator = YouTubeStreamExtractor()
    cookies = extrator._load_all_cookies()
    print(f"Contas carregadas: {len(cookies)}")
    print(f"Detalhes: {cookies}")
    # Ambos devem ser rejeitados
    assert len(cookies) == 0, "Deveria rejeitar ambos os cookies inválidos"
    print("✓ PASSOU: Múltiplas contas processadas, todas rejeitadas corretamente")


def test_pot_provider_url():
    """Teste 4: Variável de PO Token provider."""
    print("\n=== TESTE 4: PO Token Provider URL ===")
    # Limpar env vars
    for key in list(os.environ.keys()):
        if 'YTDLP' in key:
            del os.environ[key]
    
    # Configurar PO Token provider
    os.environ['YTDLP_POT_PROVIDER_URL'] = 'https://example.com/pot-provider'
    
    extrator = YouTubeStreamExtractor()
    opts = extrator._build_options(use_next_cookie=False)
    
    print(f"PO Token URL configurada: {os.environ.get('YTDLP_POT_PROVIDER_URL')}")
    print(f"Opções geradas: {bool(opts)}")
    # Deve ter carregado a opcao PO Token via extractor_args
    assert 'extractor_args' in opts, "Deveria ter extractor_args"
    print("✓ PASSOU: PO Token provider URL carregado nos extractor_args")


def test_syntax():
    """Teste 5: Verificação de sintaxe."""
    print("\n=== TESTE 5: Sintaxe Python ===")
    import py_compile
    try:
        py_compile.compile('/home/castro_war/Documentos/Worktable/farmarmoney/freedownloader/youtube_extractor.py', doraise=True)
        py_compile.compile('/home/castro_war/Documentos/Worktable/farmarmoney/freedownloader/app.py', doraise=True)
        print("✓ PASSOU: Sintaxe OK em ambos os arquivos")
    except py_compile.PyCompileError as e:
        print(f"✗ FALHOU: Erro de sintaxe: {e}")
        return False
    return True


if __name__ == '__main__':
    print("=" * 60)
    print("TESTES DE ROTAÇÃO DE COOKIES E PO TOKEN PROVIDER")
    print("=" * 60)
    
    tests = [
        test_no_cookies,
        test_legacy_single_cookie,
        test_multiple_invalid_cookies,
        test_pot_provider_url,
        test_syntax,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            result = test()
            if result is False:
                failed += 1
            else:
                passed += 1
        except Exception as e:
            print(f"✗ ERRO: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"RESULTADO: {passed} passou, {failed} falhou")
    print("=" * 60)
    
    sys.exit(0 if failed == 0 else 1)
