# Prebuilt deploy — expects .next/standalone to already exist from local build
# Canonical Next.js standalone pattern: copy ALL of standalone/ not just the project subdir
FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs \
  && adduser --system --uid 1001 nextjs

# Copy the entire standalone output (shared node_modules + project subdir)
COPY --chown=nextjs:nodejs .next/standalone/ ./
# Set working directory to the project subdir where server.js lives
WORKDIR /app/FlowmannerV2-frontend
# Static assets must be under .next/static (may not be in standalone output)
COPY --chown=nextjs:nodejs .next/static ./.next/static
# Public dir
COPY --chown=nextjs:nodejs public ./public

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
CMD ["node", "server.js"]
