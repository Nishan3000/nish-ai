# Nova AI frontend — multi-stage build for a small production image
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
# The API URL is baked in at build time for NEXT_PUBLIC_ vars.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
# Non-root user
RUN addgroup -S nova && adduser -S nova -G nova
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
USER nova
EXPOSE 3000
CMD ["node", "server.js"]
