package com.outfit.chat.controller;

import com.outfit.chat.dto.ApiResponse;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

/**
 * 全局异常处理：参数校验失败统一返回 {code:400, message:原因}，
 * 前端拿到的错误结构与其他接口一致，不用特判。
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.OK) // 业务参数错误仍走 200 + code 字段，与 FastAPI 侧风格一致
    public ApiResponse<Map<String, Object>> badRequest(IllegalArgumentException e) {
        return ApiResponse.error(400, e.getMessage());
    }

    @ExceptionHandler(Exception.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public ApiResponse<Map<String, Object>> serverError(Exception e) {
        return ApiResponse.error(500, "服务内部错误：" + e.getMessage());
    }
}
