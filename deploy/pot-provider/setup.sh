#!/bin/bash
# Setup script para POT provider em VPS
# Uso: bash setup.sh

set -e

echo "🚀 POT Provider Setup"
echo "===================="
echo ""

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Validações
if [ "$EUID" -eq 0 ]; then
  echo -e "${RED}❌ Não execute como root${NC}"
  exit 1
fi

# Verificar Docker
if ! command -v docker &> /dev/null; then
  echo -e "${RED}❌ Docker não instalado${NC}"
  exit 1
fi

# Entrada de dados
read -p "Domínio (ex: pot.example.com): " DOMAIN
read -p "Token de autenticação (deixar em branco para gerar): " AUTH_TOKEN

if [ -z "$AUTH_TOKEN" ]; then
  AUTH_TOKEN=$(openssl rand -hex 32)
  echo -e "${YELLOW}⚠️  Token gerado: $AUTH_TOKEN${NC}"
fi

# Criar diretórios
INSTALL_PATH="/opt/pot-provider"
echo -e "${YELLOW}📁 Criando diretórios em $INSTALL_PATH${NC}"
sudo mkdir -p $INSTALL_PATH/{config,certs,logs}
sudo chown $USER:$USER $INSTALL_PATH

# Copiar configurações
echo -e "${YELLOW}📋 Copiando nginx.conf${NC}"
sed "s/pot.example.com/$DOMAIN/g; s/seu-secret-token-aqui/$AUTH_TOKEN/g" nginx.conf > $INSTALL_PATH/nginx.conf

echo -e "${YELLOW}📋 Copiando docker-compose.yml${NC}"
cp docker-compose.yml $INSTALL_PATH/

# Gerar certificados (Let's Encrypt)
read -p "Gerar certificados Let's Encrypt agora? (s/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Ss]$ ]]; then
  if ! command -v certbot &> /dev/null; then
    echo -e "${YELLOW}📦 Instalando Certbot${NC}"
    sudo apt-get update && sudo apt-get install -y certbot
  fi
  
  echo -e "${YELLOW}🔐 Gerando certificados para $DOMAIN${NC}"
  sudo certbot certonly --standalone -d $DOMAIN
  
  echo -e "${YELLOW}📂 Copiando certificados${NC}"
  sudo cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem $INSTALL_PATH/certs/cert.pem
  sudo cp /etc/letsencrypt/live/$DOMAIN/privkey.pem $INSTALL_PATH/certs/key.pem
  sudo chown $USER:$USER $INSTALL_PATH/certs/*
fi

# Configurar firewall
read -p "Configurar UFW firewall? (s/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Ss]$ ]]; then
  echo -e "${YELLOW}🔒 Configurando firewall${NC}"
  sudo ufw allow 22/tcp  # SSH
  sudo ufw allow 80/tcp  # HTTP
  sudo ufw allow 443/tcp # HTTPS
  
  # Perguntar se quer habilitar UFW
  if ! sudo ufw status | grep -q "Status: active"; then
    read -p "Habilitar UFW? (s/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Ss]$ ]]; then
      sudo ufw --force enable
    fi
  fi
  
  echo -e "${GREEN}✅ Firewall configurado${NC}"
  sudo ufw status
fi

# Iniciar containers
cd $INSTALL_PATH
echo -e "${YELLOW}🐳 Iniciando Docker containers${NC}"
docker-compose up -d

echo ""
echo -e "${GREEN}✅ Setup concluído${NC}"
echo ""
echo "📋 Próximas etapas:"
echo "1. Verificar logs: cd $INSTALL_PATH && docker-compose logs -f"
echo ""
echo "🔑 Configurar no freedownloader (.env):"
echo "   export YTDLP_POT_PROVIDER_URL='https://$DOMAIN'"
echo "   export YTDLP_POT_PROVIDER_SECRET='$AUTH_TOKEN'"
echo ""
echo "📝 Testar:"
echo "   curl -H 'X-PO-Token-Auth: $AUTH_TOKEN' https://$DOMAIN/health"
echo ""
