# Marker Dictionary

权威机器可读字典：`configs/triggers.yaml`；Python 枚举：`src/bplus/triggers.py`。

所有事件日志均含 participant/session、事件码和名称、实验/硬件时钟、trial/block、device、software、phase 和 meta。物理输出使用 `TriggerPulse`，禁止各范式直接操作端口；上升沿定义为 onset，结束后必须回零。

主要码段：Session 1–7；Rest 10–11；MMN 100–109；VFT 200–209；N-back 300–309；Emotion 400–412；Interview 500–509；Recovery 600–601。

