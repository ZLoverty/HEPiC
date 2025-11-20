import sys
from importlib.metadata import packages_distributions, version, PackageNotFoundError

def _get_package_info():
    # 1. 获取当前模块的“导入名” (即文件夹名，例如 hepic)
    # __package__ 是 Python 内置变量，自动指向当前包名
    import_name = __package__ or "unknown"
    
    # 2. 反查这个导入名属于哪个“安装包” (即 pyproject.toml 里的 name)
    # 比如: 映射关系可能是 {'hepic': ['HEPiC']}
    # 注意：packages_distributions 返回的是字典，value 是列表
    dists = packages_distributions() 
    dist_names = dists.get(import_name, [])
    
    # 通常一个文件夹只对应一个包，取第一个即可
    dist_name = dist_names[0] if dist_names else import_name

    # 3. 获取版本
    try:
        dist_version = version(dist_name)
    except PackageNotFoundError:
        dist_version = "unknown"

    return dist_name, dist_version

# 执行获取，导出常量
__app_name__, __version__ = _get_package_info()

# 测试打印 (仅在直接运行此文件时显示)
if __name__ == "__main__":
    print(f"Import Name (Folder): {__package__}")
    print(f"Dist Name (PyPI):     {__app_name__}")
    print(f"Version:              {__version__}")