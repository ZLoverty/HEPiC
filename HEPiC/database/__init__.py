"""
数据库模块

提供数据模型和数据库操作接口
"""

from .material_database import MaterialDatabase, get_material_database

__all__ = ["MaterialDatabase", "get_material_database"]
