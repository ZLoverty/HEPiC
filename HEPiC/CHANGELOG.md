# 更新日志

## v1.5.2

### 材料数据库同步

- **新增腾讯云 COS 备用同步通道**：当 GitHub 无法访问时（例如境内网络对 GitHub 访问受限/较慢），`sync_materials()` 自动切换到腾讯云 COS 镜像下载材料库（固定的 `manifest.json` / `materials.zip` / `materials.zip.sha256` 三个对象），下载后同样校验 sha256 通过才原子替换本地缓存；仅在 GitHub 本身不可达时才会触发该回退，而非本地已是最新版本时也去请求 COS。
- **修复缓存目录曾回退到内置快照后无法再次生效同步结果的问题**：`MaterialDatabase.load()` 此前会复用上一次已回退为内置快照的 `materials_dir`，导致 `sync_materials()` 后续同步成功、缓存已更新，再次调用 `load()` 时仍读取的是旧的内置快照数据；现在每次 `load()` 都会重新从配置目录解析，确保读到最新同步结果。

### 质检模式

- **质检历史记录持久化到本地 SQLite**：新增 `qc_history_store`，质检完成后的记录（时间、材料、pi_code、力值均值/标准差）保存到本机 SQLite 数据库（`qc_history.sqlite3`），不再随应用重启丢失；HEPiC 桌面端与 hepic_device 嵌入式后端共用该实现，各自在本机保存独立的历史文件。
- **历史面板改为按日期分组显示**：加粗日期标题分隔不同日期的记录，便于查看跨天的历史数据。
