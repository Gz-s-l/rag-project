# 云服务器上线指南（从零到 `https://你的域名`）

> 适用场景：**手上还没有服务器**，计划用 Git 拉代码部署，并且要有域名 + HTTPS。
> 已经有服务器、只想跑起来的话看 `DEPLOY.md` 就够了，本文是它前面缺的那一段。
>
> 全程分两个阶段，**不要跳过阶段一直接上域名**：
> - 阶段一：用 `http://服务器IP:8081` 把链路跑通（不涉及域名、证书、备案）
> - 阶段二：接域名 + 自动 HTTPS

---

## 一、买服务器：怎么选

### 1. 配置

| 项 | 建议 | 原因 |
|---|---|---|
| CPU / 内存 | **2 核 4G 起**（最低 2 核 2G + swap） | 构建期是内存高峰：Maven 编译 ~1G、`pip install chromadb` 编译 ~1G、vite 打包 ~0.5G。2G 内存不配 swap 大概率 OOM 被杀 |
| 系统盘 | 40G+ | 镜像约 2.5G（AI 服务 1.5G + 后端 180M + 前端 60M + MySQL 600M），加数据卷和构建缓存 |
| 带宽 | 1~3 Mbps 够用 | 页面只有 72KB JS，SSE 传的是文字流；大模型请求是**服务器出网**，不走用户带宽 |
| 地域 | 见下方备案说明 | 直接影响能不能马上用域名 |

> 学生认证机型（阿里云/腾讯云都有）性价比最高，2C4G 一年通常只要百元级，先跑通完全够用。

### 2. 系统镜像

选 **Ubuntu 22.04 LTS** 或 **Debian 12**。这两个是 Docker 官方一等支持，下面的命令都能直接复制。
不建议 CentOS 7（已停止维护，Docker 源也难配）、不建议宝塔面板镜像（会占掉 80/443，和本项目的 Caddy 冲突）。

### 3. 备案（关键，别买错了才发现）

| 服务器地域 | 域名能否直接用 | 说明 |
|---|---|---|
| 中国大陆（北京/上海/杭州/广州等） | ❌ 需先 ICP 备案 | 未备案域名解析到大陆服务器，80/443 访问会被阻断。备案通常 1~3 周，需要域名实名 + 服务器符合要求 |
| 中国香港 / 新加坡 / 日本等境外地域 | ✅ 可直接用 | 无需备案，配置好解析就能上证书。代价是同配置价格略高、大陆访问延迟高 30~80ms |

**建议**：想当天上线选中国香港节点；如果要长期在国内用且能等备案，选大陆节点。
`http://IP:8081` 这种 IP 直连方式，两种地域都不受备案影响，所以阶段一总能先跑通。

---

## 二、首次登录与基础安全

买完在控制台"重置密码"或绑定 SSH 密钥，然后本地连上去（Windows 用 PowerShell 自带 ssh）：

```bash
ssh root@你的服务器IP
```

> 阿里云/腾讯云轻量默认用户可能是 `root`，也可能是 `ubuntu`，以控制台显示为准。

基础加固（可选但建议）：

```bash
# 更新系统
apt update && apt upgrade -y

# 时间同步（SSE 时间戳、聊天记录时间都依赖它）
timedatectl set-timezone Asia/Shanghai
```

---

## 三、安装 Docker 与 Compose

```bash
# 阿里云镜像脚本装 Docker（国内网络比官方 get.docker.com 稳）
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun

# 开机自启 + 立刻启动
systemctl enable --now docker

# 验证：两个命令都要有输出
docker version
docker compose version      # 需要 v2，输出形如 v2.29.x
```

如果 `docker compose version` 报错说没有该子命令，装一下插件：

```bash
apt install -y docker-compose-plugin
```

### 配置镜像加速（强烈建议）

国内直接拉 `mysql:8.0`、`caddy:2-alpine`、`node:20` 会非常慢甚至超时。用阿里云给你的专属加速地址：

> 阿里云控制台 → 容器镜像服务 ACR → 镜像工具 → **镜像加速器** → 复制形如 `https://xxxx.mirror.aliyuncs.com` 的地址

```bash
mkdir -p /etc/docker
tee /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": ["https://把这里换成你的专属地址.mirror.aliyuncs.com"],
  "log-driver": "json-file",
  "log-opts": { "max-size": "20m", "max-file": "3" }
}
EOF
systemctl restart docker
docker info | grep -A3 "Registry Mirrors"    # 确认生效
```

> `log-opts` 那两行是防止容器日志把磁盘写满，长期运行必备。

---

## 四、加 swap（2G / 4G 内存机器必做）

构建时内存打满会被内核直接 kill，日志里只看到 `exit code 137`，很难排查。加 2G swap 一步解决：

```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

free -h        # 确认 Swap 一行有 2.0Gi
```

---

## 五、放行端口

两处都要放行，只放一处是最常见的"服务起来了但打不开"。

### 1. 云厂商安全组（控制台操作）

| 端口 | 用途 | 是否必须 |
|---|---|---|
| 22 | SSH 登录 | 必须 |
| 8081 | 阶段一 IP 直连访问前端 | 阶段一必须；上了 HTTPS 后可关 |
| 80 | Let's Encrypt 证书校验 + HTTP 跳转 | 阶段二必须 |
| 443 | HTTPS | 阶段二必须 |

> 腾讯云**轻量应用服务器**在"防火墙"页里配，不是安全组，别找错地方。
> 安全组入站规则里**不要**放行 3306（MySQL）、8080（后端）、8000（AI 服务），它们只在 Docker 内网通信，暴露出去等于把数据库和内部接口挂公网。

### 2. 系统防火墙（如果开了 ufw）

```bash
ufw status              # 若显示 inactive 就跳过本节
ufw allow 22,80,443,8081/tcp
```

---

## 六、拉代码

仓库地址（你现有 remote）：`https://github.com/Gz-s-l/rag-project.git`

```bash
mkdir -p /opt && cd /opt
git clone https://github.com/Gz-s-l/rag-project.git outfit
cd outfit/outfit-chat        # 新架构在仓库的 outfit-chat 子目录里
```

> 仓库根目录还有原 Streamlit 单机版（`app_qa.py`、根级 `chroma_db/` 等），部署时不需要它们，
> 忽略即可；所有 docker 命令都在 `outfit-chat/` 里执行。

**如果是私有仓库**，用 Personal Access Token 代替密码（GitHub 已不支持密码认证）：

```bash
git clone https://<用户名>:<token>@github.com/Gz-s-l/rag-project.git outfit
# token 在 GitHub → Settings → Developer settings → Personal access tokens 生成，勾 repo 权限
```

国内服务器直连 GitHub 经常只有几十 KB/s，两个办法：
1. 在 Gitee 导入该仓库，服务器从 Gitee 拉（最快）；
2. 本地 `git bundle` 打包后 scp 上传。

拉完确认关键目录都在：

```bash
ls ai-service/corpus/ | head        # 应有 00~13 共 14 个 txt
ls docker-compose.yml Caddyfile init.sql
```

> `ai-service/chroma_db/` 和 `md5.txt` **不在仓库里是有意为之**：向量库由容器首次启动时从 `corpus/` 自动重建，避免本地调试数据被带上线。

---

## 七、配置 .env

```bash
cp .env.example .env
nano .env
```

至少要改两个值：

```ini
DASHSCOPE_API_KEY=sk-你的真实Key
MYSQL_ROOT_PASSWORD=换一个强密码       # 不要用 123456
```

阶段二再回来填域名：

```ini
DOMAIN=chat.你的域名.com
```

`.env` 已在 `.gitignore` 里，不会被提交。注意 **MySQL 密码只在数据卷首次初始化时生效**，后面改密码要删卷重建（会丢聊天记录）。

---

## 八、阶段一：先用 IP 验证链路

```bash
cd /opt/outfit/outfit-chat
docker compose up -d --build          # 首次构建 5~15 分钟，取决于网络
docker compose ps                     # 四个服务应为 Up，mysql 有 (healthy)
docker compose logs -f backend        # 另开一个窗口看启动，Ctrl+C 退出
```

浏览器打开 `http://服务器IP:8081`，发一句"我175，130斤，上课穿什么"。

**判定标准**（三条都要满足）：

1. 回答是**逐字蹦出来**的，不是卡几秒后整段出现；
2. 关闭页面重进，历史消息还在（说明 MySQL 落库成功）；
3. `docker compose logs ai-service` 里能看到知识库构建完成，形如 `corpus 入库完成 … 共 17 条`。

命令行快速验收：

```bash
# AI 服务知识库状态（容器内网访问，不需要对外暴露端口）
docker compose exec ai-service python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/api/knowledge/status').read().decode())"

# 从宿主机验证流式输出（逐行出现就说明没被缓冲）
curl -N "http://127.0.0.1:8081/api/chat/stream?sessionId=smoke&question=你好&userId=1"
```

> 阶段一不通就别往下走。上 HTTPS 只会多一层，不会修好底下的问题。

---

## 九、阶段二：域名 + HTTPS

### 1. 解析域名

在域名服务商（阿里云/腾讯云/Cloudflare）加一条 A 记录：

| 主机记录 | 记录类型 | 记录值 |
|---|---|---|
| `chat` | A | 你的服务器公网 IP |

生效后本地验证（必须返回你的服务器 IP 再往下走，否则证书申请必失败）：

```bash
ping chat.你的域名.com
```

### 2. 填域名并启用 Caddy

```bash
cd /opt/outfit/outfit-chat
nano .env        # DOMAIN=chat.你的域名.com

docker compose --profile https up -d
docker compose logs -f caddy     # 看证书申请过程
```

日志里出现 `certificate obtained successfully` 就成功了。首次申请约 10~40 秒。

### 3. 验证

浏览器打开 `https://chat.你的域名.com`：

- 地址栏锁形图标正常，无"不安全"提示；
- 访问 `http://chat.你的域名.com` 会自动跳转到 https；
- **再发一次消息，确认仍然逐字输出**（Caddyfile 里已对 `/api/*` 关闭压缩和缓冲，这一步是验证它真的生效）。

### 4. 上证书后收个尾

确认 HTTPS 稳定后，可以把 8081 从安全组关掉，只留 80/443：

```bash
# 云控制台关掉 8081，然后只保留 HTTPS 入口映射
# （可选）让 frontend 不再对外暴露端口：注释 docker-compose.yml 里 frontend 的 ports 段
```

---

## 十、上线验收清单

| # | 检查项 | 命令 / 观察点 |
|---|---|---|
| 1 | 四个容器 Up，mysql 健康 | `docker compose ps` |
| 2 | 外网 HTTPS 可访问 | 手机流量（非同一 WiFi）打开域名 |
| 3 | 逐字流式输出 | 回答应一段段蹦，不是整段延迟出现 |
| 4 | 聊天记录落库 | 刷新页面历史仍在 |
| 5 | 知识库就绪 | `docker compose logs ai-service` 有入库完成日志 |
| 6 | 多轮记忆 | 同一会话追问"换成上课穿"，不应重复问身高体重 |
| 7 | AI 服务重启后知识库不丢 | `docker compose restart ai-service` 后提问仍能命中语料 |
| 8 | 数据卷存在 | `docker volume ls` 有 `outfit_mysql_data`、`outfit_ai_data`、`outfit_caddy_data` |
| 9 | 证书会自动续期 | Caddy 后台自动续，无需 cron；注意别删 `caddy_data` 卷 |

---

## 十一、日常运维

```bash
cd /opt/outfit/outfit-chat

# 更新代码（改了 corpus 或代码后）
git pull
docker compose up -d --build        # 只会重建有变化的镜像

# 看日志
docker compose logs -f --tail=100 backend ai-service

# 重启某个服务
docker compose restart ai-service

# 备份 MySQL（聊天记录）
docker compose exec -T mysql sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" outfit_chat' > backup_$(date +%F).sql

# 磁盘占用排查
docker system df
docker image prune -f               # 清理无用镜像层（不会删运行中的）
```

---

## 十二、常见故障

### 1. 构建到一半 `exit code 137` / `Killed`

内存不够。加 swap（第四节），或临时给构建限并发：

```bash
docker compose build --build-arg MAVEN_OPTS="-Xmx512m" backend
```

### 2. 构建卡在 `pip install` 很久

`.env` 里确认 `PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`（模板里已默认），改完重新 `--build`。

### 3. `ai-service` 构建报 `chroma-hnswlib` 编译错误

镜像里已装 `build-essential` + `cmake`。若仍失败，把日志贴出来，通常是 Python 版本与 wheel 不匹配。

### 4. 页面能打开，但发消息 502

```bash
docker compose ps                       # backend 是否在 Up
docker compose logs --tail=50 backend
```
多数是 MySQL 还没起来就启动 backend。等 30 秒或 `docker compose restart backend`。

### 5. Caddy 报 `no such host` / 证书一直不下来

按顺序查：
1. `ping 域名` 是否解析到本机 IP（最常见原因：解析还没生效）；
2. 安全组/防火墙是否放行 80（Let's Encrypt 必须从 80 端口校验）；
3. 大陆服务器：域名是否已备案（未备案会被拦截，表面现象就是证书申请超时）；
4. 80 端口是否被别的服务占用：`ss -lntp | grep :80`（装了宝塔/nginx 的机器常见）。

### 6. HTTPS 页面能开，但消息不逐字出来

Caddyfile 的 `/api/*` 分支必须保留 `flush_interval -1` 且**不要**加 `encode`。改完执行 `docker compose --profile https restart caddy`。

### 7. 服务器重启后服务没起来

各服务已配 `restart: unless-stopped`，正常会自动拉起。若没有：

```bash
systemctl is-enabled docker     # 应为 enabled
docker compose up -d            # 手动拉起（不要加 --build）
```

---

## 附：本文与其它文档的关系

| 文档 | 用途 |
|---|---|
| `DEPLOY_CLOUD.md`（本文） | 从买服务器到域名 HTTPS 的全流程 |
| `DEPLOY.md` | 部署细节、配置项说明、SSE 分层排查、备份恢复、生产建议 |
| `ai-service/README.md` / `backend/README.md` / `frontend/README.md` | 各模块接口契约与本地开发 |

**尚未实机验证的部分**：本文所有命令基于标准 Ubuntu/Debian + Docker 环境编写，但镜像构建与容器内运行尚未在真实服务器上跑过（开发机无 Docker）。首次 `--build` 如报错，优先看第十二节，仍未解决把完整日志发出来。
