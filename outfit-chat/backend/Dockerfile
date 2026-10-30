# =====================================================================
# 模块四：SpringBoot 主后端镜像（多阶段构建）
#   阶段1 maven：编译打包出 jar
#   阶段2 jre  ：只放运行时，镜像更小（~180MB）
# 构建：docker build -t outfit-backend:1.0.0 ./backend
# =====================================================================

# ---------- 阶段 1：编译 ----------
FROM maven:3.9-eclipse-temurin-17 AS builder

WORKDIR /build

# 用阿里云镜像加速依赖下载（国内构建必需，海外构建也不影响）
COPY docker/maven-settings.xml /root/.m2/settings.xml

# 先只拷 pom 拉依赖，充分利用层缓存：源码改动不会触发重新下载
# 用 dependency:resolve 而不是 go-offline（后者对插件解析更严格，偶发失败会阻断构建）
COPY pom.xml .
RUN mvn -B -q dependency:resolve || true

# 再拷源码编译（跳过测试：本模块的验证靠本地联调，镜像构建不应依赖外部服务）
COPY src ./src
RUN mvn -B -q clean package -DskipTests

# ---------- 阶段 2：运行 ----------
FROM eclipse-temurin:17-jre-alpine

ENV TZ=Asia/Shanghai \
    JAVA_OPTS="-Xms256m -Xmx512m -Dfile.encoding=UTF-8"

WORKDIR /app

# busybox wget 自带，健康检查不需要额外装 curl
COPY --from=builder /build/target/chat-backend-1.0.0.jar app.jar

EXPOSE 8080

# 健康检查：查一个一定会返回 200 的接口（空会话历史）
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD wget -qO- http://127.0.0.1:8080/api/chat/history/healthcheck >/dev/null 2>&1 || exit 1

# 显式指定端口：容器里不受宿主 SERVER__PORT 之类环境变量干扰
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar --server.port=8080"]
