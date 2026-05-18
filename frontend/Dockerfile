FROM node:24-alpine AS builder

WORKDIR /app

ARG VITE_API_URL=
ARG VITE_BASE_PATH=/

ENV VITE_API_URL=${VITE_API_URL} \
    VITE_BASE_PATH=${VITE_BASE_PATH}

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
