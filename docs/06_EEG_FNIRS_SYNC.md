# EEG-fNIRS 同步

三级同步：事件日志/软件时钟、LSL 统一时间轴、硬件 TTL。正式 NVC 以真实设备导出时间轴和共同事件为准。

当前安全脉宽 100 ms；LIGHTNIRS 锁存未知。在确认锁存前不得缩短。fNIRS 当前 75 ms 采样间隔导致事件量化，MMN 毫秒级分析只信 EEG；NVC 离线重采样信号但不重采样事件。

真机步骤：发 10 个已知码 → CURRY/LIGHTNIRS 分别导出 → `scripts/sync_check.py compare` → 检查丢失、重复、offset、jitter、漂移。未经真机验证不得声称同步完成。

