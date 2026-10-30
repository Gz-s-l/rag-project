package com.outfit.chat.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * 跨域配置（开发期全放行）。
 *
 * <p>模块三的 Vue 前端跑在 http://localhost:5173（vite 默认端口），
 * 直接调本服务的 SSE 和历史接口会有跨域限制，这里先全部放开；
 * 生产环境用 nginx 反代同域后，这段配置可以收紧或删掉。</p>
 *
 * <p>注意：SSE（EventSource）同样受 CORS 约束，所以 GET /api/chat/stream 必须在这里放行。</p>
 */
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                // allowedOrigins("*") 与 allowCredentials(true) 冲突，用 originPatterns 代替
                .allowedOriginPatterns("*")
                .allowedMethods("GET", "POST", "DELETE", "OPTIONS")
                .allowedHeaders("*")
                .maxAge(3600);
    }
}
