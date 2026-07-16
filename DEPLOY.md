# Guía de despliegue en VPS (Hetzner CX22)

## 1. Provisionar el servidor

1. Crea un servidor en [Hetzner Cloud](https://console.hetzner.cloud/):
   - Tipo: **CX22** (~4 €/mes) — 2 vCPU, 4 GB RAM, 40 GB disco
   - Imagen: **Ubuntu 24.04**
   - Añade tu clave SSH pública

2. Apunta tu dominio al IP del servidor:
   ```
   A    yourdomain.com    → <IP del servidor>
   ```
   Espera a que el DNS propague antes de continuar (puede tardar hasta 24h, normalmente <5 min).

---

## 2. Configurar el servidor

```bash
# Conectar
ssh root@<IP>

# Actualizar sistema
apt update && apt upgrade -y

# Instalar Docker
curl -fsSL https://get.docker.com | sh

# Añadir usuario no-root (opcional pero recomendado)
adduser deploy
usermod -aG docker deploy
```

---

## 3. Subir el código

```bash
# Desde tu máquina local
git clone <tu-repo> /opt/forecast-money
# o bien:
rsync -avz --exclude='node_modules' --exclude='*.db' --exclude='.git' \
  ./ deploy@<IP>:/opt/forecast-money/
```

---

## 4. Crear backend/.env.prod

```bash
cd /opt/forecast-money

# Generar una SECRET_KEY aleatoria de 64 caracteres
python3 -c "import secrets; print(secrets.token_hex(32))"

# Crear el archivo
cat > backend/.env.prod << 'EOF'
SECRET_KEY=<pega aquí el resultado del comando anterior>
COOKIE_SECURE=true
ALLOWED_ORIGINS=https://yourdomain.com
ACCESS_TOKEN_EXPIRE_MINUTES=10080
DATA_DIR=/app/backend/data
AUTH_DB_PATH=/app/backend/data/auth.db
USERS_DATA_DIR=/app/backend/data/users
EOF

chmod 600 backend/.env.prod
```

---

## 5. Configurar el dominio en Caddyfile

```bash
# Editar Caddyfile y reemplazar "yourdomain.com" con tu dominio real
nano Caddyfile
```

---

## 6. Crear directorio de datos y lanzar

```bash
mkdir -p data/users

# Construir imágenes y lanzar en modo producción
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Caddy obtiene automáticamente el certificado SSL de Let's Encrypt en el primer arranque.

---

## 7. Registrar el primer usuario

Visita `https://yourdomain.com/login` y crea tu cuenta.

Si prefieres hacerlo por CLI:

```bash
curl -X POST https://yourdomain.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "tu@email.com", "password": "contraseña-segura", "name": "Tu nombre"}'
```

---

## 8. Comandos útiles

```bash
# Ver logs en tiempo real
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f

# Reiniciar un servicio
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart backend

# Actualizar código
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Backup de datos
tar -czf backup-$(date +%Y%m%d).tar.gz data/
```

---

## 9. Instalar la PWA en Android (Web Share Target)

1. Abre Chrome en Android y navega a `https://yourdomain.com`.
2. Chrome mostrará un banner "Añadir a pantalla de inicio" — acéptalo.
3. En la app del banco, exporta el extracto y pulsa **Compartir**.
4. Selecciona **Forecast Money** en el menú de compartir.
5. La app se abre directamente en `/upload` con el archivo pre-cargado.

> **Nota:** El Web Share Target solo funciona cuando la app está instalada como PWA
> (añadida a la pantalla de inicio). En el navegador normal, el share va al OS, no a la web app.

---

## Seguridad: lista de verificación

- [ ] `SECRET_KEY` de 64+ caracteres aleatorios, nunca en el repositorio
- [ ] `COOKIE_SECURE=true` en producción (cookie solo se envía por HTTPS)
- [ ] `ALLOWED_ORIGINS` apunta solo a tu dominio, no a `*`
- [ ] El puerto 8000 y 3000 no están expuestos directamente — solo Caddy en 80/443
- [ ] `backend/.env.prod` tiene permisos `600`
- [ ] Firewall del servidor: solo puertos 22 (SSH), 80 y 443 abiertos

```bash
# Hetzner tiene firewall en el panel web, o puedes usar ufw:
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```
