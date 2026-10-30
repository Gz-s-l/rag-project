package com.outfit.chat.dto;

import java.util.List;

/**
 * 统一响应包装（与 FastAPI 侧的 {code, message, data} 结构保持一致，
 * 前端可以用同一套响应处理逻辑）。
 *
 * @param code    0=成功，非 0=失败
 * @param message 提示信息
 * @param data    业务数据
 */
public record ApiResponse<T>(int code, String message, T data) {

    public static <T> ApiResponse<T> ok(T data) {
        return new ApiResponse<>(0, "success", data);
    }

    public static <T> ApiResponse<T> error(int code, String message) {
        return new ApiResponse<>(code, message, null);
    }

    /** 兼容 List 场景的静态工厂（消除泛型数组告警） */
    public static <T> ApiResponse<List<T>> okList(List<T> data) {
        return new ApiResponse<>(0, "success", data);
    }
}
