"""
材料属性数据库模块

提供材料信息的存储和查询功能
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional


class MaterialDatabase:
    """材料属性数据库"""
    
    def __init__(self, db_file: Optional[Path] = None):
        """
        初始化材料数据库
        
        参数:
            db_file: 数据库文件路径，如果为None则使用默认路径
        """
        self.logger = logging.getLogger(__name__)
        
        if db_file is None:
            # 使用默认路径：database/material_properties.json
            db_file = Path(__file__).parent / "material_properties.json"
        
        self.db_file = db_file
        self.materials = {}
        self.load()
    
    def load(self):
        """从文件加载材料数据"""
        if self.db_file.exists():
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    self.materials = json.load(f)
                self.logger.info(f"Loaded {len(self.materials)} materials from {self.db_file}")
            except Exception as e:
                self.logger.error(f"Failed to load material database: {e}")
                self._init_default_materials()
        else:
            self.logger.warning(f"Material database file not found: {self.db_file}")
            self._init_default_materials()
    
    def _init_default_materials(self):
        """初始化默认材料数据"""
        self.materials = {
            "PLA": {
                "name": "聚乳酸 (PLA)",
                "expected_force": 5.0,
                "force_range": [3.0, 7.0],
                "temperature": 200,
                "speed": 30,
                "description": "通用 3D 打印材料，易于打印",
                "stability_threshold": 2.0,
            },
            "PETG": {
                "name": "聚对苯二甲酸乙二酯 (PETG)",
                "expected_force": 6.0,
                "force_range": [4.0, 8.0],
                "temperature": 230,
                "speed": 25,
                "description": "高强度材料，耐用性好",
                "stability_threshold": 2.5,
            },
            "TPU": {
                "name": "热塑性聚氨酯 (TPU)",
                "expected_force": 3.0,
                "force_range": [1.5, 4.5],
                "temperature": 210,
                "speed": 20,
                "description": "柔性材料，适合制作橡胶类部件",
                "stability_threshold": 1.5,
            },
            "ABS": {
                "name": "丙烯腈-丁二烯-苯乙烯共聚物 (ABS)",
                "expected_force": 7.0,
                "force_range": [5.0, 9.0],
                "temperature": 240,
                "speed": 20,
                "description": "高强度，耐冲击",
                "stability_threshold": 3.0,
            },
            "尼龙": {
                "name": "聚酰胺 (尼龙)",
                "expected_force": 8.0,
                "force_range": [6.0, 10.0],
                "temperature": 250,
                "speed": 15,
                "description": "高强度，低摩擦",
                "stability_threshold": 3.5,
            },
        }
        self.logger.info("Initialized with default materials")
    
    def save(self):
        """保存材料数据到文件"""
        try:
            self.db_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.materials, f, ensure_ascii=False, indent=2)
            self.logger.info(f"Saved {len(self.materials)} materials to {self.db_file}")
        except Exception as e:
            self.logger.error(f"Failed to save material database: {e}")
    
    def get_material(self, name: str) -> Optional[Dict[str, Any]]:
        """获取材料信息"""
        return self.materials.get(name)
    
    def get_all_materials(self) -> Dict[str, Dict[str, Any]]:
        """获取所有材料信息"""
        return self.materials.copy()
    
    def get_material_names(self) -> list:
        """获取所有材料名称"""
        return list(self.materials.keys())
    
    def add_material(self, name: str, properties: Dict[str, Any]):
        """添加或更新材料"""
        self.materials[name] = properties
        self.logger.info(f"Added/Updated material: {name}")
    
    def delete_material(self, name: str) -> bool:
        """删除材料"""
        if name in self.materials:
            del self.materials[name]
            self.logger.info(f"Deleted material: {name}")
            return True
        return False
    
    def get_forcerange(self, name: str) -> tuple:
        """获取材料的力值范围"""
        material = self.get_material(name)
        if material:
            force_range = material.get('force_range', [0, 0])
            return tuple(force_range)
        return (0, 0)
    
    def get_expected_force(self, name: str) -> float:
        """获取材料的预期挤出力"""
        material = self.get_material(name)
        return material.get('expected_force', 0.0) if material else 0.0
    
    def get_temperature(self, name: str) -> float:
        """获取材料的打印温度"""
        material = self.get_material(name)
        return material.get('temperature', 0.0) if material else 0.0
    
    def get_speed(self, name: str) -> float:
        """获取材料的打印速度"""
        material = self.get_material(name)
        return material.get('speed', 0.0) if material else 0.0
    
    def get_stability_threshold(self, name: str) -> float:
        """获取材料的稳定性阈值"""
        material = self.get_material(name)
        return material.get('stability_threshold', 2.0) if material else 2.0


# 全局数据库实例
_global_db = None


def get_material_database() -> MaterialDatabase:
    """获取全局材料数据库实例"""
    global _global_db
    if _global_db is None:
        _global_db = MaterialDatabase()
    return _global_db
