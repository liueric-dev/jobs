# Mirrors Apify's ts-start template (apify/actor-templates, templates/ts-start).
# Build stage: compile TypeScript.
FROM apify/actor-node:24 AS builder
COPY --chown=myuser:myuser package*.json ./
RUN npm ci --include=dev --audit=false
COPY --chown=myuser:myuser . ./
RUN npm run build

# Runtime stage: production dependencies and the compiled output only.
FROM apify/actor-node:24
COPY --chown=myuser:myuser package*.json ./
RUN npm ci --omit=dev --omit=optional --audit=false && rm -rf ~/.npm
COPY --from=builder --chown=myuser:myuser /usr/src/app/dist ./dist
COPY --chown=myuser:myuser .actor ./.actor
CMD ["node", "dist/main.js"]
