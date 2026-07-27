"""Ordered workflow dependency catalog."""

from __future__ import annotations

from timelapse_manager.dependency_manager.models import DependencySpec


CATALOG = (
    DependencySpec(
        "camera",
        "拍摄组件",
        None,
        "Camera Timelapse Controller",
        "执行包围曝光延时拍摄",
        True,
        "python:camera",
        "安装 / 更新",
    ),
    DependencySpec(
        "gphoto2",
        "拍摄组件",
        "camera",
        "gPhoto2",
        "Camera Timelapse 的相机控制工具",
        True,
        "system:gphoto2",
    ),
    DependencySpec(
        "bracketlapse",
        "后期组件",
        None,
        "Bracketlapse",
        "合成包围曝光照片并生成视频",
        True,
        "python:bracketlapse",
        "安装 / 更新",
    ),
    DependencySpec(
        "enfuse",
        "后期组件",
        "bracketlapse",
        "enfuse",
        "Hugin 提供的曝光融合工具",
        True,
        "system:hugin",
    ),
    DependencySpec(
        "ffmpeg",
        "后期组件",
        "bracketlapse",
        "FFmpeg",
        "将融合帧编码为延时视频",
        True,
        "system:ffmpeg",
    ),
    DependencySpec(
        "align_image_stack",
        "后期组件",
        "bracketlapse",
        "align_image_stack",
        "启用 Bracketlapse 对齐模式时使用",
        False,
        "system:hugin",
    ),
    DependencySpec(
        "sunsetscore",
        "晚霞评分组件",
        None,
        "SunsetScore",
        "分析 HDR 照片中的晚霞强度",
        False,
        "python:sunsetscore",
        "安装 / 更新",
    ),
    DependencySpec(
        "sunset_runtime",
        "晚霞评分组件",
        "sunsetscore",
        "llama.cpp 推理运行时",
        "SunsetScore 自动选择的本地推理后端",
        False,
        "sunset:prepare",
        "准备资源",
    ),
    DependencySpec(
        "sunset_model",
        "晚霞评分组件",
        "sunsetscore",
        "Qwen3-VL 语言模型",
        "Q4_K_M 模型，约 1.11 GB",
        False,
    ),
    DependencySpec(
        "sunset_projector",
        "晚霞评分组件",
        "sunsetscore",
        "Qwen3-VL 视觉投影模型",
        "Q8_0 视觉投影，约 445 MB",
        False,
    ),
)

CATALOG_BY_ID = {item.identifier: item for item in CATALOG}
