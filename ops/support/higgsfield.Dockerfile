# Open Higgsfield AI (https://github.com/Autom8AI/Open-Higgsfield-AI) as a web app.
#
# The project publishes desktop installers and a Next.js app but no Dockerfile,
# so this one follows its README: `npm run setup`, `npm run build`, `npm run start`.
# It is a front end only. Every generation is billed to a Muapi.ai API key that
# each person pastes into their own browser (the app keeps it in localStorage), so
# the server holds no secret. Keep it behind an nginx-proxy-manager access list
# anyway: it is a tool for our team, not for the public internet.
#
# NOT built or run in the session that wrote it (no way to reach the box). Build it
# once by hand, read the output, and open the page before trusting it.
#
# Pin HIGGSFIELD_REF to a commit you have looked at.
FROM node:20-alpine AS build
RUN apk add --no-cache git
ARG HIGGSFIELD_REF=main
WORKDIR /app
RUN git clone https://github.com/Autom8AI/Open-Higgsfield-AI.git . \
 && git checkout "$HIGGSFIELD_REF"
RUN npm run setup && npm run build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app /app
EXPOSE 3000
CMD ["npm", "run", "start"]
