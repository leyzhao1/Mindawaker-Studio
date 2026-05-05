"""
项目日志配置
统一处理日志输出，支持控制台和文件
"""
import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logger(
    name: str = "mw_3d_t2i",
    log_dir: str = "./data/logs",
    log_level: int = logging.INFO,
    console_output: bool = True
) -> logging.Logger:
    """
    设置日志记录器

    Args:
        name: 日志记录器名称
        log_dir: 日志文件目录
        log_level: 日志级别
        console_output: 是否同时输出到控制台

    Returns:
        配置好的日志记录器
    """
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # 避免重复添加处理器
    if logger.handlers:
        return logger

    # 创建日志目录
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 文件处理器 - 按日期命名
    date_str = datetime.now().strftime("%Y%m%d")
    log_file = log_path / f"{name}_{date_str}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 控制台处理器
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def get_logger(name: str = "mw_3d_t2i") -> logging.Logger:
    """获取已配置的日志记录器"""
    return logging.getLogger(name)


# 便捷函数
def log_info(msg: str, *args, **kwargs):
    """记录INFO级别日志"""
    logger = get_logger()
    logger.info(msg, *args, **kwargs)


def log_debug(msg: str, *args, **kwargs):
    """记录DEBUG级别日志"""
    logger = get_logger()
    logger.debug(msg, *args, **kwargs)


def log_warning(msg: str, *args, **kwargs):
    """记录WARNING级别日志"""
    logger = get_logger()
    logger.warning(msg, *args, **kwargs)


def log_error(msg: str, *args, **kwargs):
    """记录ERROR级别日志"""
    logger = get_logger()
    logger.error(msg, *args, **kwargs)


# 应用启动时初始化日志
logger = setup_logger()
