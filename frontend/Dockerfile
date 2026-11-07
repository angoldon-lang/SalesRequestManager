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
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
