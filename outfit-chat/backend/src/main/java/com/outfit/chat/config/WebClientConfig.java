package com.outfit.chat.config;

import io.netty.channel.ChannelOption;
import io.netty.handler.timeout.ReadTimeoutHandler;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

/**
 * WebClient 配置：专门用于调用 FastAPI 的 SSE 流式接口。
 *
 * <p>要点：</p>
 * <ul>
 *   <li>超时策略用「读空闲超时」（ReadTimeoutHandler）：SSE 流式回答期间，
 *       只要模型还在逐字吐字，连接就一直保持；只有整整 responseTimeoutMs
 *       毫秒收不到任何字节才判定超时，避免长回答被整体响应超时掐断；</li>
 *   <li>本服务同时引了 spring-boot-starter-web（MVC 对外服务）和
 *       spring-boot-starter-webflux（只用 WebClient，不起 WebFlux 容器），
 *       MVC 自动成为主容器，互不干扰。</li>
 * </ul>
 */
@Configuration
@EnableConfigurationProperties(AiServiceProperties.class)
public class WebClientConfig {

    @Bean
    public WebClient aiWebClient(AiServiceProperties props) {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, (int) props.connectTimeoutMs())
                .doOnConnected(conn -> conn
                        .addHandlerLast(new ReadTimeoutHandler(props.responseTimeoutMs(), TimeUnit.MILLISECONDS)));

        return WebClient.builder()
                .baseUrl(props.baseUrl())
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
