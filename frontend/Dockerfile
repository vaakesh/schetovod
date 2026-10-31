FROM node:22.21.0-alpine AS dev

WORKDIR /frontend

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

FROM dev AS build

RUN npm run build

# the last stage is what a build without a target produces
FROM nginx:1.29.0-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx.static.conf /etc/nginx/frontend.conf
COPY --from=build /frontend/dist /usr/share/nginx/html
