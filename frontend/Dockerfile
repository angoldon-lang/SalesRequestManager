FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_AZ_CLIENT_ID=""
ARG VITE_AZ_TENANT_ID=""
ENV VITE_AZ_CLIENT_ID=$VITE_AZ_CLIENT_ID VITE_AZ_TENANT_ID=$VITE_AZ_TENANT_ID
RUN npm run build

FROM nginx:1.27-alpine
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf.in /etc/nginx/srm.conf.in
COPY 05-srm-listen.sh /docker-entrypoint.d/05-srm-listen.sh
RUN chmod +x /docker-entrypoint.d/05-srm-listen.sh
COPY --from=build /app/dist /usr/share/nginx/html
