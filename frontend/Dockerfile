# Frontend (Next.js) image
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM deps AS dev
WORKDIR /app
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:7200
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV PORT=3200
EXPOSE 3200
CMD ["npm", "run", "dev"]

FROM deps AS builder
WORKDIR /app
COPY . .
# NEXT_PUBLIC_* vars are inlined at build time
ARG NEXT_PUBLIC_API_URL=http://localhost:7200
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
# Next standalone server reads PORT (default 3000)
ENV PORT=3200
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3200
CMD ["node", "server.js"]
