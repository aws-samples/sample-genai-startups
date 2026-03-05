FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json ./
RUN npm install

COPY tsconfig.json ./
COPY src/ ./src/
RUN npm run build


FROM node:20-alpine

WORKDIR /app

ENV NODE_ENV=production

RUN addgroup -S agentcore && adduser -S bedrock_agentcore -G agentcore

COPY package.json ./
RUN npm install --omit=dev

COPY --from=builder /app/dist ./dist

# AgentCore Runtime service contract ports
# https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html
# 8080: HTTP Mode
EXPOSE 8080

USER bedrock_agentcore

CMD ["node", "--require", "@aws/aws-distro-opentelemetry-node-autoinstrumentation/register", "dist/index.js"]
