# Stage 1: build fat JAR
FROM maven:3.9-amazoncorretto-21-alpine AS builder
WORKDIR /build
COPY pom.xml .
RUN mvn dependency:go-offline -q
COPY src/ src/
RUN mvn package -q -DskipTests

# Stage 2: lean runtime
FROM amazoncorretto:21-alpine
WORKDIR /app

RUN addgroup -S agentcore && adduser -S bedrock_agentcore -G agentcore

COPY --from=builder /build/target/*.jar app.jar
RUN chown bedrock_agentcore:agentcore app.jar

# AgentCore Runtime service contract: POST /invocations and GET /ping on port 8080
# https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html
EXPOSE 8080

USER bedrock_agentcore

CMD ["java", "-jar", "app.jar"]
