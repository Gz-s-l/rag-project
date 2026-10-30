# =====================================================================
# 模块四：前端镜像（Vue3 构建 → nginx 托管静态资源 + 反代 /api）
# 构建：docker build -t outfit-frontend:1.0.0 ./frontend
# =====================================================================

# ---------- 阶段 1：构建 ----------
FROM node:20-alpine AS builder

WORKDIR /build

# 国内加速（npmmirror）；海外构建同样可用
RUN npm config set registry https://registry.npmmirror.com

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build

# ---------- 阶段 2：nginx 托管 ----------
FROM nginx:1.27-alpine

ENV TZ=Asia/Shanghai

# 站点配置：静态资源 + /api 反向代理到 SpringBoot（含 SSE 专用参数）
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1
