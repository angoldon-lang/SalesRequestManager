#!/bin/sh
set -e
if [ -f /certs/tls.crt ] && [ -f /certs/tls.key ]; then
  LISTEN="listen 8080 ssl;"
  TLS="ssl_certificate /certs/tls.crt; ssl_certificate_key /certs/tls.key; ssl_protocols TLSv1.2 TLSv1.3;"
  echo "SRM: HTTPS attivo (certificati in /certs)"
else
  LISTEN="listen 8080;"
  TLS=""
  echo "SRM: HTTP (nessun certificato in /certs)"
fi
sed -e "s|#LISTEN#|$LISTEN|" -e "s|#TLS#|$TLS|" /etc/nginx/srm.conf.in > /etc/nginx/conf.d/default.conf
